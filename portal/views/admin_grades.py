from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string

from academics.models import AcademicEnrollment, EC, ECGrade, Semester
from academics.services.grading import apply_ec_grade, compute_ec_status, resolve_threshold
from academics.services.semester import compute_semester_result
from academics.services.ue import compute_ue_result
from academics.services.workflow import can_publish_semester, get_semester_permissions
from accounts.access import can_access, get_user_scope
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


def _build_excel_row(enrollment, semester, ues, index, active_session_type="normal", updated_ec_id=None):
    threshold = resolve_threshold(enrollment)
    permissions = get_semester_permissions(semester)
    can_edit_current_session = (
        permissions["can_enter_retake"]
        if active_session_type == "retake"
        else permissions["can_enter_normal"]
    )
    grades_by_ec_id = {
        grade.ec_id: grade
        for grade in ECGrade.objects.filter(
            enrollment=enrollment,
            ec__ue__semester=semester,
        ).select_related("ec")
    }

    ue_blocks = []
    for ue in ues:
        ue_result = compute_ue_result(ue, enrollment)
        ec_rows = []

        for row in ue_result["rows"]:
            grade = grades_by_ec_id.get(row["ec"].id)
            edit_score = None
            final_score = None
            if grade:
                edit_score = grade.retake_score if active_session_type == "retake" else grade.normal_score
                final_score = grade.final_score
            ec_status = compute_ec_status(final_score, threshold)
            display_status = (
                compute_ec_status(grade.normal_score if grade else None, threshold)
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

    return {
        "index": index,
        "enrollment": enrollment,
        "student_id": enrollment.student.student_profile.id,
        "semester_id": semester.id,
        "student_profile_id": enrollment.student.student_profile.id,
        "student_name": enrollment.student.student_profile.full_name,
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
        "updated_ec_id": updated_ec_id,
    }


@login_required
def save_grade(request):
    if request.method != "POST":
        return HttpResponse("Methode non autorisee", status=405)

    if not can_access(request.user, "view_portal", "dashboard"):
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
            "academic_year",
        ),
        pk=enrollment_id,
    )
    ec = get_object_or_404(
        EC.objects.select_related("ue", "ue__semester", "ue__semester__academic_class"),
        pk=ec_id,
    )
    semester = ec.ue.semester
    permissions = get_semester_permissions(semester)
    if session_type == "retake":
        if not permissions["can_enter_retake"]:
            return HttpResponse("Le rattrapage n'est pas autorise pour ce semestre.", status=403)
    else:
        if not permissions["can_enter_normal"]:
            return HttpResponse("La saisie normale n'est pas autorisee pour ce semestre.", status=403)

    if raw_note:
        try:
            note = Decimal(raw_note)
        except (InvalidOperation, TypeError):
            return HttpResponse("Note invalide", status=400)

        if note < Decimal("0") or note > Decimal("20"):
            return HttpResponse("La note doit etre comprise entre 0 et 20.", status=400)

        grade, _ = ECGrade.objects.get_or_create(
            enrollment=enrollment,
            ec=ec,
        )
        if session_type == "retake":
            grade.retake_score = note
        else:
            grade.normal_score = note
        apply_ec_grade(grade)
        grade.save()
        grade.refresh_from_db()
    else:
        grade = ECGrade.objects.filter(enrollment=enrollment, ec=ec).first()
        if grade:
            if session_type == "retake":
                grade.retake_score = None
            else:
                grade.normal_score = None
            apply_ec_grade(grade)
            if grade.normal_score is None and grade.retake_score is None:
                grade.delete()
            else:
                grade.save()

    ues = list(semester.ues.prefetch_related("ecs__grades").order_by("id"))
    compute_ue_result(ec.ue, enrollment)
    compute_semester_result(semester, enrollment)

    class_enrollments = list(_get_class_enrollments(enrollment.academic_class, enrollment.academic_year))
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

    html = render_to_string(
        "portal/admin/grades/partials/excel_row.html",
        {"row": row},
        request=request,
    )
    return HttpResponse(html)


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
    workflow_permissions = get_semester_permissions(semester)
    requested_session_type = request.GET.get("session", "normal").strip().lower() or "normal"
    if requested_session_type not in {"normal", "retake"}:
        requested_session_type = "normal"
    if requested_session_type == "retake" and not workflow_permissions["can_enter_retake"]:
        active_session_type = "normal"
    elif requested_session_type == "normal" and not workflow_permissions["can_enter_normal"] and workflow_permissions["can_enter_retake"]:
        active_session_type = "retake"
    else:
        active_session_type = requested_session_type
    active_session_label = "Rattrapage" if active_session_type == "retake" else "Normale"
    class_enrollments = list(_get_class_enrollments(academic_class, enrollment.academic_year))
    ues = list(semester.ues.prefetch_related("ecs__grades").order_by("id"))
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

    return render(
        request,
        "portal/admin/grades/excel_sheet.html",
        {
            "enrollment": enrollment,
            "academic_class": academic_class,
            "semester": semester,
            "ues": ues,
            "rows": rows,
            "active_session_type": active_session_type,
            "active_session_label": active_session_label,
            "workflow_permissions": workflow_permissions,
            "publish_ready": publish_ready,
            "workflow_badge": _get_workflow_badge(semester),
        },
    )
