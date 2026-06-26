from datetime import date
from decimal import Decimal, InvalidOperation

from django.utils.text import slugify

from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string

from academic_cycle.models import GradeModificationRequest
from academic_cycle.services.grade_modifications import (
    GradeModificationError,
    confirm_grade_modification,
    request_grade_modification,
)
from academics.models import AcademicEnrollment, EC, ECGrade, Semester
from academics.services.grading import apply_ec_grade, compute_ec_status, resolve_ec_threshold, resolve_threshold
from academics.services.semester import compute_semester_result
from academics.services.ue import compute_ue_result
from academics.services.workflow import can_publish_semester, get_semester_permissions
from accounts.access import can_access, get_user_position, get_user_scope
from accounts.dashboards.helpers import get_user_branch
from portal.services.it_support_service import log_support_action
from portal.models import SupportAuditLog
from portal.services.notes_workflow import can_edit_retake_grade
from secretary.permissions import is_secretary


def get_post_login_portal_url(user):
    scope = get_user_scope(user)
    role = scope.get("role")

    if is_secretary(user):
        return "/secretary/"

    if role == "super_admin" and can_access(user, "view_portal", "dashboard"):
        return "/portal/admin/grades/"

    if role == "student" and can_access(user, "view_portal", "student"):
        return "/portal/student/"

    if role == "teacher" and can_access(user, "view_portal", "teacher"):
        return "/portal/teacher/"

    if role in {"staff_admin", "directeur_etudes"} and can_access(user, "view_portal", "staff"):
        return "/portal/staff/"

    return "/portal/"


@login_required
def portal_dashboard(request):
    scope = get_user_scope(request.user)
    role = scope.get("role")

    if role == "super_admin" and can_access(request.user, "view_portal", "dashboard"):
        return admin_grade_dashboard(request)

    return HttpResponseForbidden("Acces refuse.")


@login_required
def admin_grade_dashboard(request):
    if not can_access(request.user, "view_portal", "dashboard"):
        return HttpResponseForbidden("Acces refuse.")

    enrollments = (
        AcademicEnrollment.objects
        .select_related(
            "student__student_profile__inscription__candidature",
            "academic_class",
            "academic_year",
            "branch",
            "programme",
        )
        .order_by("academic_class__level", "student__student_profile__inscription__candidature__last_name")
    )

    return render(
        request,
        "portal/admin/grades/dashboard.html",
        {
            "enrollments": enrollments,
        },
    )


@login_required
def load_student_results(request, enrollment_id):
    if not can_access(request.user, "view_portal", "dashboard"):
        return HttpResponseForbidden("Acces refuse.")

    enrollment = get_object_or_404(
        AcademicEnrollment.objects.select_related(
            "student__student_profile__inscription__candidature",
            "academic_class",
        ),
        pk=enrollment_id,
    )

    semesters = enrollment.academic_class.semesters.all().order_by("number")
    results = [compute_semester_result(semester, enrollment) for semester in semesters]

    return render(
        request,
        "portal/admin/grades/partials/student_result.html",
        {
            "enrollment": enrollment,
            "results": results,
        },
    )


@login_required
def load_grades_table(request, enrollment_id, semester_id):
    if not can_access(request.user, "view_portal", "dashboard"):
        return HttpResponseForbidden("Acces refuse.")

    enrollment = get_object_or_404(
        AcademicEnrollment.objects.select_related(
            "student__student_profile__inscription__candidature",
            "academic_class",
        ),
        pk=enrollment_id,
    )
    semester = get_object_or_404(
        Semester.objects.select_related("academic_class"),
        pk=semester_id,
    )

    ues = semester.ues.prefetch_related("ecs").order_by("id")

    return render(
        request,
        "portal/admin/grades/partials/grades_table.html",
        {
            "enrollment": enrollment,
            "semester": semester,
            "ues": ues,
        },
    )


def _get_class_enrollments(academic_class, academic_year):
    return (
        AcademicEnrollment.objects
        .filter(
            academic_class=academic_class,
            academic_year=academic_year,
            is_active=True,
        )
        .select_related(
            "student__student_profile__inscription__candidature",
            "academic_class",
        )
        .order_by(
            "student__student_profile__inscription__candidature__last_name",
            "student__student_profile__inscription__candidature__first_name",
        )
    )


def _format_decimal(value):
    if value in (None, ""):
        return ""
    return f"{Decimal(value):.2f}".replace(".", ",")


def _format_input_decimal(value):
    if value in (None, ""):
        return ""
    return f"{Decimal(value):.2f}"


def _get_workflow_badge(semester):
    status_icons = {
        Semester.STATUS_DRAFT: "&#9203;",
        Semester.STATUS_NORMAL_ENTRY: "&#9203;",
        Semester.STATUS_NORMAL_LOCKED: "&#128274;",
        Semester.STATUS_RETAKE_ENTRY: "&#9203;",
        Semester.STATUS_FINALIZED: "&#10004;",
        Semester.STATUS_PUBLISHED: "&#10004;",
    }
    return {
        "code": semester.status,
        "label": semester.get_status_display(),
        "icon": status_icons.get(semester.status, "&#9203;"),
    }


def _resolve_active_session_type(requested_session_type, workflow_permissions):
    requested_session_type = (requested_session_type or "normal").strip().lower() or "normal"
    if requested_session_type not in {"normal", "retake"}:
        requested_session_type = "normal"
    if requested_session_type == "retake" and not workflow_permissions["can_enter_retake"]:
        return "normal"
    if (
        requested_session_type == "normal"
        and not workflow_permissions["can_enter_normal"]
        and workflow_permissions["can_enter_retake"]
    ):
        return "retake"
    return requested_session_type


def _get_notes_grid_ues(semester):
    """Retourne la hiérarchie canonique UE -> EC utilisée par toute la maquette.

    Important: les headers du template et les lignes étudiantes doivent dériver de la
    même structure ordonnée, sinon les colspans se décalent et le bloc résultat semestre
    se retrouve visuellement déplacé.
    """

    return list(
        semester.ues.prefetch_related(
            Prefetch(
                "ecs",
                queryset=EC.objects.order_by("id"),
            )
        ).order_by("id")
    )


def _build_notes_grid_context(*, academic_class, semester, requested_session_type):
    workflow_permissions = get_semester_permissions(semester)
    active_session_type = _resolve_active_session_type(requested_session_type, workflow_permissions)
    active_session_label = "Rattrapage" if active_session_type == "retake" else "Normale"
    first_enrollment = (
        AcademicEnrollment.objects.filter(
            academic_class=academic_class,
            academic_year=academic_class.academic_year,
            is_active=True,
        )
        .select_related("student__student_profile")
        .order_by(
            "student__student_profile__inscription__candidature__last_name",
            "student__student_profile__inscription__candidature__first_name",
        )
        .first()
    )
    class_enrollments = list(_get_class_enrollments(academic_class, academic_class.academic_year))
    ues = _get_notes_grid_ues(semester)
    publish_ready = can_publish_semester(semester, class_enrollments)

    rows = [
        _build_excel_row(
            enrollment=enr,
            semester=semester,
            ues=ues,
            index=index,
            active_session_type=active_session_type,
        )
        for index, enr in enumerate(class_enrollments, start=1)
    ]

    return {
        "academic_class": academic_class,
        "semester": semester,
        "ues": ues,
        "rows": rows,
        "active_session_type": active_session_type,
        "active_session_label": active_session_label,
        "workflow_permissions": workflow_permissions,
        "publish_ready": publish_ready,
        "workflow_badge": _get_workflow_badge(semester),
        "first_enrollment": first_enrollment,
    }


def _build_excel_row(enrollment, semester, ues, index, active_session_type="normal", updated_ec_id=None):
    permissions = get_semester_permissions(semester)
    can_edit_current_session = (
        permissions["can_enter_retake"]
        if active_session_type == "retake"
        else permissions["can_enter_normal"
    ])
    grades_by_ec_id = {
        grade.ec_id: grade
        for grade in ECGrade.objects.filter(
            enrollment=enrollment,
            ec__ue__semester=semester,
        ).select_related("ec")
    }

    ue_blocks = []
    ue_results_by_id = {
        ue.id: compute_ue_result(ue, enrollment)
        for ue in ues
    }

    for ue in ues:
        ue_result = ue_results_by_id[ue.id]
        ue_rows_by_ec_id = {
            item["ec"].id: item
            for item in ue_result["rows"]
        }
        ec_rows = []

        # IMPORTANT: on itère sur la même hiérarchie EC que celle utilisée par le header.
        # Ainsi, le nombre de cellules par UE reste strictement identique entre header et body.
        for ec in ue.ecs.all():
            ec_threshold = resolve_ec_threshold(ec.coefficient)
            row = ue_rows_by_ec_id.get(ec.id, {
                "ec": ec,
                "note_coefficient": Decimal("0.00"),
                "credit_obtained": Decimal("0.00"),
                "credit_required": ec.credit_required,
                "is_validated": False,
            })
            grade = grades_by_ec_id.get(ec.id)
            edit_score = None
            final_score = None
            if grade:
                edit_score = grade.retake_score if active_session_type == "retake" else grade.normal_score
                final_score = grade.final_score
            is_retake_editable = can_edit_retake_grade(grade=grade, threshold=ec_threshold)
            ec_status = compute_ec_status(final_score, ec_threshold)
            display_status = (
                compute_ec_status(grade.normal_score if grade else None, ec_threshold)
                if active_session_type == "normal"
                else ec_status
            )
            ec_rows.append({
                "ec": row["ec"],
                "grade_id": grade.id if grade else "",
                "note": final_score if final_score is not None else "",
                "note_display": _format_decimal(final_score),
                "note_input_value": _format_input_decimal(edit_score),
                "normal_score": grade.normal_score if grade else "",
                "normal_score_display": _format_decimal(grade.normal_score) if grade else "",
                "retake_score": grade.retake_score if grade else "",
                "retake_score_display": _format_decimal(grade.retake_score) if grade else "",
                "final_score": final_score if final_score is not None else "",
                "final_score_display": _format_decimal(final_score),
                "has_retake_score": bool(grade and grade.retake_score is not None),
                "is_retake_editable": is_retake_editable,
                "status": ec_status,
                "display_status": display_status,
                "note_coefficient": row["note_coefficient"],
                "note_coefficient_display": _format_decimal(row["note_coefficient"]),
                "credit_obtained": row["credit_obtained"],
                "credit_obtained_display": _format_decimal(row["credit_obtained"]),
                "credit_required": row["credit_required"],
                "is_validated": row["is_validated"],
            })

        ue_blocks.append({
            "ue": ue,
            "rows": ec_rows,
            "average": ue_result["average"],
            "average_display": _format_decimal(ue_result["average"]),
            "total_note_coefficients": ue_result["total_note_coefficients"],
            "total_note_coefficients_display": _format_decimal(ue_result["total_note_coefficients"]),
            "credit_obtained": ue_result["credit_obtained"],
            "credit_obtained_display": _format_decimal(ue_result["credit_obtained"]),
            "credit_required": ue_result["credit_required"],
            "total_coefficients": ue_result["total_coefficients"],
        })

    semester_result = compute_semester_result(semester, enrollment)
    report_lock_reason = ""
    if not permissions["can_generate_reports"]:
        if semester.status == Semester.STATUS_FINALIZED:
            report_lock_reason = "Releves disponibles apres publication par la direction."
        elif permissions["can_publish"]:
            report_lock_reason = "Publier le semestre pour activer les releves."
        else:
            report_lock_reason = f"Releves indisponibles: statut {semester.get_status_display()}."

    return {
        "index": index,
        "enrollment": enrollment,
        "student_id": enrollment.student.student_profile.id,
        "semester_id": semester.id,
        "student_profile_id": enrollment.student.student_profile.id,
        "student_matricule": enrollment.student.student_profile.matricule,
        "student_name": enrollment.student.student_profile.full_name,
        "student_first_name": enrollment.student.student_profile.inscription.candidature.first_name,
        "student_last_name": enrollment.student.student_profile.inscription.candidature.last_name,
        "ue_blocks": ue_blocks,
        "semester_average": semester_result["average"],
        "semester_average_display": _format_decimal(semester_result["average"]),
        "semester_percentage": semester_result["percentage"],
        "semester_percentage_display": _format_decimal(semester_result["percentage"]),
        "semester_credits": semester_result["credit_obtained"],
        "semester_credits_display": _format_decimal(semester_result["credit_obtained"]),
        "semester_required_credits": semester_result["credit_required"],
        "semester_required_credits_display": _format_decimal(semester_result["credit_required"]),
        "semester_total_coefficients": semester_result["total_coefficients"],
        "semester_total_coefficients_display": _format_decimal(semester_result["total_coefficients"]),
        "active_session_type": active_session_type,
        "can_edit_current_session": can_edit_current_session,
        "can_generate_reports": permissions["can_generate_reports"],
        "report_lock_reason": report_lock_reason,
        "updated_ec_id": updated_ec_id,
    }


# Statuts de semestre pour lesquels une session est consideree "cloturee"
# (donc eligible a une correction via OTP, plutot qu'a un blocage sec). Le
# statut "jamais ouvert" (DRAFT pour le normal, DRAFT/NORMAL_ENTRY pour le
# rattrapage) reste bloque sans OTP : il n'y a rien a "corriger".
NORMAL_CLOSED_STATUSES = {
    Semester.STATUS_NORMAL_LOCKED,
    Semester.STATUS_RETAKE_ENTRY,
    Semester.STATUS_FINALIZED,
    Semester.STATUS_PUBLISHED,
}
RETAKE_CLOSED_STATUSES = {
    Semester.STATUS_FINALIZED,
    Semester.STATUS_PUBLISHED,
}


@login_required
def save_grade(request):
    if request.method != "POST":
        return HttpResponse("Methode non autorisee", status=405)

    is_it_support = get_user_position(request.user) == "it_support"
    if not can_access(request.user, "view_portal", "dashboard") and not is_it_support:
        return HttpResponseForbidden("Acces refuse.")

    enrollment_id = request.POST.get("enrollment_id")
    ec_id = request.POST.get("ec_id")
    session_type = request.POST.get("session_type", "normal").strip().lower() or "normal"
    if session_type not in {"normal", "retake"}:
        session_type = "normal"
    raw_note = request.POST.get("note", "").strip().replace(",", ".")

    enrollment = get_object_or_404(
        AcademicEnrollment.objects.select_related(
            "student__student_profile__inscription__candidature",
            "academic_class",
            "academic_class__branch",
            "academic_year",
            "branch",
        ),
        pk=enrollment_id,
    )
    ec = get_object_or_404(
        EC.objects.select_related("ue", "ue__semester", "ue__semester__academic_class"),
        pk=ec_id,
    )
    semester = ec.ue.semester
    if is_it_support:
        user_branch = get_user_branch(request.user)
        if user_branch is None or enrollment.branch_id != user_branch.id or semester.academic_class.branch_id != user_branch.id:
            return HttpResponseForbidden("Action hors annexe refusee.")
    if ec.ue.semester.academic_class_id != enrollment.academic_class_id:
        return HttpResponse("EC hors classe.", status=400)

    permissions = get_semester_permissions(semester)
    if session_type == "retake":
        if not permissions["can_enter_retake"]:
            if request.POST.get("live") == "1" and semester.status in RETAKE_CLOSED_STATUSES:
                return _request_grade_otp(request, enrollment=enrollment, ec=ec, session_type=session_type, raw_note=raw_note)
            return HttpResponse("Le rattrapage n'est pas autorise pour ce semestre.", status=403)
    else:
        if not permissions["can_enter_normal"]:
            if request.POST.get("live") == "1" and semester.status in NORMAL_CLOSED_STATUSES:
                return _request_grade_otp(request, enrollment=enrollment, ec=ec, session_type=session_type, raw_note=raw_note)
            return HttpResponse("La saisie normale n'est pas autorisee pour ce semestre.", status=403)

    if raw_note:
        try:
            note = Decimal(raw_note)
        except (InvalidOperation, TypeError):
            return HttpResponse("Note invalide", status=400)

        if note < Decimal("0") or note > Decimal("20"):
            return HttpResponse("La note doit etre comprise entre 0 et 20.", status=400)

        ec_threshold = resolve_ec_threshold(ec.coefficient)
        if session_type == "retake":
            grade = ECGrade.objects.filter(enrollment=enrollment, ec=ec).first()
            if not can_edit_retake_grade(grade=grade, threshold=ec_threshold):
                return HttpResponse("Seules les matieres non validees peuvent etre modifiees au rattrapage.", status=403)
            if grade is None:
                return HttpResponse("Note normale requise avant saisie du rattrapage.", status=400)
            grade.retake_score = note
        else:
            grade, _ = ECGrade.objects.get_or_create(
                enrollment=enrollment,
                ec=ec,
            )
            grade.normal_score = note
        apply_ec_grade(grade)
        grade.save()
        grade.refresh_from_db()
    else:
        grade = ECGrade.objects.filter(enrollment=enrollment, ec=ec).first()
        if grade:
            ec_threshold = resolve_ec_threshold(ec.coefficient)
            if session_type == "retake":
                if not can_edit_retake_grade(grade=grade, threshold=ec_threshold):
                    return HttpResponse("Seules les matieres non validees peuvent etre modifiees au rattrapage.", status=403)
                grade.retake_score = None
            else:
                grade.normal_score = None
            apply_ec_grade(grade)
            if grade.normal_score is None and grade.retake_score is None:
                grade.delete()
            else:
                grade.save()

    ues = _get_notes_grid_ues(semester)
    compute_ue_result(ec.ue, enrollment)
    compute_semester_result(semester, enrollment)

    class_enrollments = list(_get_class_enrollments(enrollment.academic_class, enrollment.academic_year))
    if is_it_support:
        log_support_action(
            actor=request.user,
            branch=get_user_branch(request.user),
            action_type=SupportAuditLog.ACTION_GRADE_UPDATED,
            target_user=enrollment.student,
            target_label=f"Note {ec.title} - {enrollment.academic_class.display_name}",
            details=f"Modification note {session_type}.",
        )
    enrollment_index = next(
        (idx for idx, item in enumerate(class_enrollments, start=1) if item.pk == enrollment.pk),
        1,
    )

    row = _build_excel_row(
        enrollment=enrollment,
        semester=semester,
        ues=ues,
        index=enrollment_index,
        active_session_type=session_type,
        updated_ec_id=ec.id,
    )

    if request.POST.get("live") == "1":
        # Grille instantanee du dashboard informaticien (maquette.html) :
        # le client a deja recalcule l'affichage a la frappe (hx-swap="none"
        # cote input). On ne renvoie que la reconciliation serveur via des
        # swaps hors-bande, sans jamais toucher aux <input>.
        target_ec_row, target_ue_block = None, None
        for ue_block in row["ue_blocks"]:
            for ec_row in ue_block["rows"]:
                if ec_row["ec"].id == ec.id:
                    target_ec_row, target_ue_block = ec_row, ue_block
                    break
            if target_ec_row:
                break
        html = render_to_string(
            "portal/admin/grades/partials/row_oob.html",
            {"row": row, "ec_row": target_ec_row, "ue_block": target_ue_block},
            request=request,
        )
    else:
        html = render_to_string(
            "portal/admin/grades/partials/excel_row.html",
            {"row": row, "active_session_type": session_type},
            request=request,
        )
    response = HttpResponse(html)
    response["HX-Trigger"] = '{"kpi-update": "", "workflow-update": ""}'
    return response


def _request_grade_otp(request, *, enrollment, ec, session_type, raw_note):
    """
    Correction d'une note deja saisie dans une session deja cloturee
    (dashboard informaticien uniquement, cf. CAHIER_DES_CHARGES_OTP_NOTES.md).

    Ne s'applique qu'a une CORRECTION d'une note existante : si aucune note
    n'a jamais ete saisie pour ce couple enrollment/EC/session, le blocage
    normal (403) reste en vigueur, OTP ou pas.
    """
    if not raw_note:
        return HttpResponse("La correction d'une session cloturee necessite une note.", status=400)
    try:
        note = Decimal(raw_note)
    except (InvalidOperation, TypeError):
        return HttpResponse("Note invalide", status=400)
    if note < Decimal("0") or note > Decimal("20"):
        return HttpResponse("La note doit etre comprise entre 0 et 20.", status=400)

    grade = ECGrade.objects.filter(enrollment=enrollment, ec=ec).first()
    existing_score = (grade.retake_score if session_type == "retake" else grade.normal_score) if grade else None
    if existing_score is None:
        message = (
            "Le rattrapage n'est pas autorise pour ce semestre."
            if session_type == "retake"
            else "La saisie normale n'est pas autorisee pour ce semestre."
        )
        return HttpResponse(message, status=403)

    branch = get_user_branch(request.user) or enrollment.branch
    try:
        otp_request = request_grade_modification(
            branch=branch,
            ec_grade=grade,
            session_type=session_type,
            requested_score=note,
            requested_by=request.user,
            reason=(request.POST.get("reason") or "").strip(),
        )
    except GradeModificationError as exc:
        html = render_to_string(
            "portal/admin/grades/partials/grade_otp_modal.html",
            {"otp_error": str(exc)},
            request=request,
        )
        return HttpResponse(f'<div id="it-modal-root" hx-swap-oob="true">{html}</div>')

    html = render_to_string(
        "portal/admin/grades/partials/grade_otp_modal.html",
        {
            "otp_request_id": otp_request.pk,
            "otp_validity_minutes": GradeModificationRequest.OTP_VALIDITY_MINUTES,
            "student_name": enrollment.student.get_full_name() or enrollment.student.username,
            "ec_title": ec.title,
        },
        request=request,
    )
    return HttpResponse(f'<div id="it-modal-root" hx-swap-oob="true">{html}</div>')


@login_required
def save_grade_confirm_otp(request):
    if request.method != "POST":
        return HttpResponse("Methode non autorisee", status=405)

    is_it_support = get_user_position(request.user) == "it_support"
    if not can_access(request.user, "view_portal", "dashboard") and not is_it_support:
        return HttpResponseForbidden("Acces refuse.")

    otp_request_id = request.POST.get("otp_request_id")
    otp_code = (request.POST.get("otp_code") or "").strip()

    def _apply(otp_request):
        grade = otp_request.ec_grade
        if otp_request.session_type == GradeModificationRequest.SESSION_RETAKE:
            grade.retake_score = otp_request.requested_score
        else:
            grade.normal_score = otp_request.requested_score
        apply_ec_grade(grade)
        grade.save()
        grade.refresh_from_db()
        compute_ue_result(grade.ec.ue, grade.enrollment)
        compute_semester_result(grade.ec.ue.semester, grade.enrollment)
        return {"score": str(otp_request.requested_score), "final_score": str(grade.final_score)}

    try:
        confirm_grade_modification(
            request_id=otp_request_id,
            code=otp_code,
            approver=request.user,
            apply_callback=_apply,
        )
    except (GradeModificationError, GradeModificationRequest.DoesNotExist) as exc:
        message = str(exc) if isinstance(exc, GradeModificationError) else "Demande introuvable."
        response = render(
            request,
            "portal/admin/grades/partials/grade_otp_modal.html",
            {
                "otp_request_id": otp_request_id,
                "otp_error": message,
                "otp_validity_minutes": GradeModificationRequest.OTP_VALIDITY_MINUTES,
            },
        )
        response.status_code = 400
        return response

    response = render(
        request,
        "portal/admin/grades/partials/grade_otp_modal.html",
        {"otp_success": True},
    )
    response["HX-Trigger"] = '{"kpi-update": "", "workflow-update": "", "it-modal-close": ""}'
    return response


@login_required
def publish_semester_view(request, enrollment_id, semester_id):
    if request.method != "POST":
        return HttpResponse("Methode non autorisee", status=405)

    if not can_access(request.user, "view_portal", "dashboard"):
        return HttpResponseForbidden("Acces refuse.")

    enrollment = get_object_or_404(
        AcademicEnrollment.objects.select_related("academic_class", "academic_year"),
        pk=enrollment_id,
    )
    semester = get_object_or_404(
        Semester.objects.select_related("academic_class"),
        pk=semester_id,
    )

    permissions = get_semester_permissions(semester)
    class_enrollments = list(_get_class_enrollments(enrollment.academic_class, enrollment.academic_year))

    if not permissions["can_publish"]:
        return HttpResponse("La publication n'est pas autorisee a ce stade.", status=403)

    if not can_publish_semester(semester, class_enrollments):
        return HttpResponse("Toutes les notes doivent etre renseignees avant publication.", status=400)

    semester.status = Semester.STATUS_PUBLISHED
    semester.save(update_fields=["status"])

    return redirect("accounts_portal:excel_grade_view", enrollment_id=enrollment.pk, semester_id=semester.pk)


@login_required
def excel_grade_view(request, enrollment_id, semester_id):
    """
    Vue reelle de la maquette :
    - standalone
    - sans header/footer du site
    - orientee classe + semestre
    """
    if not can_access(request.user, "view_portal", "dashboard"):
        return HttpResponseForbidden("Acces refuse.")

    enrollment = get_object_or_404(
        AcademicEnrollment.objects.select_related(
            "academic_class",
            "academic_year",
            "branch",
            "programme",
        ),
        pk=enrollment_id,
    )

    semester = get_object_or_404(
        Semester.objects.select_related(
            "academic_class",
        ),
        pk=semester_id,
    )

    academic_class = enrollment.academic_class
    context = _build_notes_grid_context(
        academic_class=academic_class,
        semester=semester,
        requested_session_type=request.GET.get("session", "normal"),
    )

    return render(
        request,
        "portal/admin/grades/excel_sheet.html",
        {
            "enrollment": enrollment,
            **context,
        },
    )


@login_required
def it_notes_grid_view(request):
    if get_user_position(request.user) != "it_support":
        return HttpResponseForbidden("Acces refuse.")

    from portal.views.it_grades_import import build_it_grade_selection_context

    selection_context = build_it_grade_selection_context(
        request.user,
        class_id=request.GET.get("class_id"),
        semester_id=request.GET.get("semester_id"),
    )
    academic_class = selection_context["selected_class"]
    semester = selection_context["selected_semester"]
    if academic_class is None or semester is None:
        return HttpResponse("Classe ou semestre invalide.", status=400)

    context = _build_notes_grid_context(
        academic_class=academic_class,
        semester=semester,
        requested_session_type=request.GET.get("session", "normal"),
    )
    return render(
        request,
        "portal/admin/grades/partials/notes_maquette.html",
        {
            **context,
            "embedded_in_dashboard": True,
        },
    )


@login_required
def it_notes_workspace_view(request):
    if get_user_position(request.user) != "it_support":
        return HttpResponseForbidden("Acces refuse.")

    from portal.views.it_grades_import import build_it_grade_selection_context

    selection_context = build_it_grade_selection_context(
        request.user,
        class_id=request.GET.get("class_id"),
        semester_id=request.GET.get("semester_id"),
    )
    return render(
        request,
        "portal/staff/partials/it_notes_workspace.html",
        selection_context,
    )


try:
    from weasyprint import HTML
except Exception:
    HTML = None


@login_required
def class_grade_sheet_pdf_view(request, class_id, semester_id):
    if get_user_position(request.user) != "it_support":
        return HttpResponseForbidden("Acces refuse.")

    if HTML is None:
        return HttpResponse(
            "WeasyPrint n'est pas installe ou ses dependances systeme sont manquantes.",
            status=500,
            content_type="text/plain; charset=utf-8",
        )

    fmt = request.GET.get("format", "a4").lower()
    if fmt not in ("a3", "a4"):
        fmt = "a4"

    from portal.views.it_grades_import import build_it_grade_selection_context

    selection_context = build_it_grade_selection_context(
        request.user,
        class_id=class_id,
        semester_id=semester_id,
    )
    academic_class = selection_context["selected_class"]
    semester = selection_context["selected_semester"]
    if academic_class is None or semester is None:
        return HttpResponse("Classe ou semestre invalide.", status=400)

    context = _build_notes_grid_context(
        academic_class=academic_class,
        semester=semester,
        requested_session_type="normal",
    )
    context["today"] = date.today()
    context["print_format"] = fmt

    ues = context.get("ues", [])
    chunk_size = 3
    context["ue_chunks"] = [ues[i:i + chunk_size] for i in range(0, len(ues), chunk_size)]

    html = render_to_string(
        "academics/reports/class_grade_sheet_pdf.html",
        context,
        request=request,
    )
    pdf_bytes = HTML(string=html, base_url=request.build_absolute_uri()).write_pdf(
        presentational_hints=True,
    )

    filename = f"releve-classe-{slugify(academic_class.name)}-s{semester.number}-{fmt}.pdf"
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Content-Length"] = len(pdf_bytes)
    return response


@login_required
def class_grade_sheet_print_view(request, class_id, semester_id):
    if get_user_position(request.user) != "it_support":
        return HttpResponseForbidden("Acces refuse.")

    fmt = request.GET.get("format", "a4").lower()
    if fmt not in ("a3", "a4"):
        fmt = "a4"

    from portal.views.it_grades_import import build_it_grade_selection_context

    selection_context = build_it_grade_selection_context(
        request.user,
        class_id=class_id,
        semester_id=semester_id,
    )
    academic_class = selection_context["selected_class"]
    semester = selection_context["selected_semester"]
    if academic_class is None or semester is None:
        return HttpResponse("Classe ou semestre invalide.", status=400)

    context = _build_notes_grid_context(
        academic_class=academic_class,
        semester=semester,
        requested_session_type="normal",
    )
    context["today"] = date.today()
    context["print_format"] = fmt

    ues = context.get("ues", [])
    chunk_size = 3
    context["ue_chunks"] = [ues[i:i + chunk_size] for i in range(0, len(ues), chunk_size)]

    return render(
        request,
        "academics/reports/class_grade_sheet_print.html",
        context,
    )
