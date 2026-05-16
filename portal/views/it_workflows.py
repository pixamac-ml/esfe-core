from __future__ import annotations

from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import FileResponse, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from academics.models import AcademicClass, EC, Semester, UE
from academics.services.semester import compute_semester_result
from accounts.access import get_user_position
from accounts.dashboards.helpers import get_user_branch
from portal.selectors import (
    get_it_academic_classes,
    get_it_semesters_for_class,
    get_it_students_for_class,
)
from portal.services.academic_structure_service import (
    archive_academic_class,
    assign_student_to_class,
    build_academic_structure_context,
    delete_ec,
    save_academic_class,
    save_ec,
    save_ue,
)
from portal.services.archive_service import (
    archive_batches_for_branch,
    archive_candidates_for_branch,
    archive_class,
    archive_detail,
    archive_year,
    preview_archive,
    restore_archive_batch,
)
from portal.services.notes_workflow import (
    apply_notes_workflow_action,
    get_available_actions,
    get_notes_state,
    get_retake_candidates,
)
from portal.services.it_support_service import get_account_support_state, get_scoped_staff_queryset
from portal.services.it_support_service import create_temp_password, log_support_action
from portal.services.informaticien_workflows import (
    build_audit_context,
    build_catalog_context,
    build_home_context,
    build_import_context,
    build_supervision_context,
    build_support_context,
    create_branch_ticket,
    create_catalog_item,
    get_branch_settings,
    import_notes_file,
    resolve_branch_ticket,
    take_branch_ticket,
    update_branch_settings,
)
from portal.selectors.informaticien import grade_entries_for_class, support_tickets_for_branch
from portal.models import SupportAuditLog, SupportTicket
from students.models import Student
from portal.views.admin_grades import _build_notes_grid_context


def _require_it_support(request):
    if get_user_position(request.user) != "it_support":
        return False
    if get_user_branch(request.user) is None:
        return False
    return True


def _same_branch_or_forbidden(*, request, target_user):
    request_branch = get_user_branch(request.user)
    target_branch = getattr(getattr(target_user, "profile", None), "branch", None)
    if request_branch is None or target_branch != request_branch:
        return False
    return True


def _resolve_workflow_selection(request):
    branch = get_user_branch(request.user)
    classes_qs = get_it_academic_classes(branch=branch)
    selected_class = None
    selected_semester = None
    semesters = []

    class_id = (request.GET.get("class_id") or request.GET.get("classe") or request.POST.get("class_id") or request.POST.get("classe") or "").strip()
    semester_id = (request.GET.get("semester_id") or request.GET.get("semester") or request.POST.get("semester_id") or request.POST.get("semester") or "").strip()
    if class_id.isdigit():
        selected_class = get_object_or_404(classes_qs, pk=int(class_id))
        semesters = list(get_it_semesters_for_class(academic_class=selected_class))

    if selected_class and semester_id.isdigit():
        selected_semester = (
            Semester.objects.select_related("academic_class")
            .filter(pk=int(semester_id), academic_class=selected_class)
            .first()
        )

    return {
        "branch": branch,
        "classes": list(classes_qs[:200]),
        "selected_class": selected_class,
        "semesters": semesters,
        "selected_semester": selected_semester,
    }


def _build_notes_workflow_context(request, *, toast=None):
    context = _resolve_workflow_selection(request)
    state = get_notes_state(
        academic_class=context["selected_class"],
        semester=context["selected_semester"],
    )
    context.update(
        {
            "workflow_module": "notes",
            "state": state,
            "actions": get_available_actions(state=state),
            "toast": toast,
        }
    )
    return context


@login_required
def it_notes_flow_workspace(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    return render(
        request,
        "portal/informaticien/workflows/notes_workspace.html",
        _build_notes_workflow_context(request),
    )


@login_required
def it_home_workspace(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    return render(
        request,
        "portal/informaticien/workflows/home_workspace.html",
        build_home_context(branch=get_user_branch(request.user)),
    )


@login_required
def it_notes_workflow_action(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    if request.method != "POST":
        return HttpResponseForbidden("Methode non autorisee.")

    context = _resolve_workflow_selection(request)
    toast = None
    successful = False
    try:
        action = (request.POST.get("action") or "").strip()
        apply_notes_workflow_action(
            actor=request.user,
            academic_class=context["selected_class"],
            semester=context["selected_semester"],
            action=action,
        )
        successful = True
        messages = {
            "verifier_notes": "Controle termine: aucune note manquante bloquante.",
            "publier_session_normale": "Session normale publiee. Le rattrapage peut maintenant etre prepare.",
            "activer_rattrapage": "Rattrapage active. Seules les notes de rattrapage restent modifiables.",
            "publier_resultats_finaux": "Resultats finaux publies. Les releves et exports sont deblocables.",
        }
        toast = {"level": "success", "message": messages.get(action, "Workflow notes mis a jour.")}
    except ValidationError as exc:
        if request.POST.get("from_modal") == "retake":
            modal_context = _build_retake_modal_context(request)
            modal_context["form_error"] = " ".join(exc.messages)
            response = render(request, "portal/informaticien/workflows/retake_modal.html", modal_context)
            response["HX-Retarget"] = "#it-modal-root"
            return response
        toast = {"level": "error", "message": " ".join(exc.messages)}

    response = render(
        request,
        "portal/informaticien/workflows/notes_workspace.html",
        _build_notes_workflow_context(request, toast=toast),
    )
    if successful:
        response["HX-Trigger"] = "it-modal-close"
    return response


def _build_retake_modal_context(request):
    context = _resolve_workflow_selection(request)
    academic_class = context["selected_class"]
    semester = context["selected_semester"]
    state = get_notes_state(academic_class=academic_class, semester=semester)
    candidates = get_retake_candidates(academic_class=academic_class, semester=semester)
    return {
        "academic_class": academic_class,
        "semester": semester,
        "state": state,
        "candidates": candidates,
        "subject_count": sum(len(candidate.failed_subjects) for candidate in candidates),
    }


@login_required
def load_notes_workspace(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")

    context = _resolve_workflow_selection(request)
    academic_class = context["selected_class"]
    semester = context["selected_semester"]
    if academic_class is None or semester is None:
        return HttpResponse(
            '<div class="workflow-grid-placeholder">Selectionne une classe et un semestre pour afficher la maquette.</div>'
        )
    if semester.status == Semester.STATUS_DRAFT:
        semester.status = Semester.STATUS_NORMAL_ENTRY
        semester.save(update_fields=["status"])

    grid_context = _build_notes_grid_context(
        academic_class=academic_class,
        semester=semester,
        requested_session_type=request.GET.get("session", "normal"),
    )
    return render(
        request,
        "portal/admin/grades/partials/notes_grid.html",
        {
            **grid_context,
            "embedded_in_dashboard": True,
        },
    )


@login_required
def it_cards_workspace(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")

    selection = _resolve_workflow_selection(request)
    students = []
    if selection["selected_class"]:
        students = list(get_it_students_for_class(academic_class=selection["selected_class"])[:80])
    selection.update({"students": students, "workflow_module": "cards"})
    return render(request, "portal/informaticien/workflows/cards_workspace.html", selection)


@login_required
def it_support_flow_workspace(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    branch = get_user_branch(request.user)
    status = (request.GET.get("status") or "").strip()
    return render(
        request,
        "portal/informaticien/workflows/support_workspace.html",
        build_support_context(branch=branch, status=status),
    )


@login_required
def it_support_flow_action(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    if request.method != "POST":
        return HttpResponseForbidden("Methode non autorisee.")

    branch = get_user_branch(request.user)
    action = (request.POST.get("action") or "").strip()
    toast = None
    try:
        if action == "create":
            create_branch_ticket(
                actor=request.user,
                branch=branch,
                title=request.POST.get("title"),
                description=request.POST.get("description"),
            )
            toast = {"level": "success", "message": "Ticket cree."}
        else:
            ticket = get_object_or_404(support_tickets_for_branch(branch=branch), pk=request.POST.get("ticket_id"))
            if action == "take":
                take_branch_ticket(actor=request.user, branch=branch, ticket=ticket)
                toast = {"level": "success", "message": "Ticket pris en charge."}
            elif action == "resolve":
                resolve_branch_ticket(
                    actor=request.user,
                    branch=branch,
                    ticket=ticket,
                    resolution=request.POST.get("resolution"),
                )
                toast = {"level": "success", "message": "Ticket resolu."}
            else:
                toast = {"level": "error", "message": "Action ticket inconnue."}
    except (ValidationError, ValueError) as exc:
        message = " ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
        toast = {"level": "error", "message": message}

    return render(
        request,
        "portal/informaticien/workflows/support_workspace.html",
        build_support_context(branch=branch, status=request.POST.get("status", ""), toast=toast),
    )


@login_required
def it_audit_workspace(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    return render(
        request,
        "portal/informaticien/workflows/audit_workspace.html",
        build_audit_context(branch=get_user_branch(request.user)),
    )


def _resolve_import_selection(request):
    selection = _resolve_workflow_selection(request)
    return selection["classes"], selection["selected_class"], selection["selected_semester"]


@login_required
def it_import_workspace(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    branch = get_user_branch(request.user)
    classes, selected_class, selected_semester = _resolve_import_selection(request)
    return render(
        request,
        "portal/informaticien/workflows/import_workspace.html",
        build_import_context(
            branch=branch,
            classes=classes,
            selected_class=selected_class,
            selected_semester=selected_semester,
        ),
    )


@login_required
def it_import_upload(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    if request.method != "POST":
        return HttpResponseForbidden("Methode non autorisee.")
    branch = get_user_branch(request.user)
    classes, selected_class, selected_semester = _resolve_import_selection(request)
    feedback = None
    upload = request.FILES.get("file")
    try:
        if selected_class is None or selected_semester is None:
            raise ValidationError("Selectionne une classe et un semestre.")
        if upload is None:
            raise ValidationError("Fichier Excel obligatoire.")
        feedback = import_notes_file(
            actor=request.user,
            branch=branch,
            academic_class=selected_class,
            semester=selected_semester,
            file=upload,
        )
    except (ValidationError, ValueError) as exc:
        message = " ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
        feedback = type("Feedback", (), {
            "level": "error",
            "message": message,
            "invalid_lines": [],
            "updated": 0,
            "skipped_empty": 0,
            "skipped_unknown_columns": 0,
            "skipped_unknown_students": 0,
            "skipped_invalid_scores": 0,
            "unknown_columns": [],
        })()
    return render(
        request,
        "portal/informaticien/workflows/import_workspace.html",
        build_import_context(
            branch=branch,
            classes=classes,
            selected_class=selected_class,
            selected_semester=selected_semester,
            feedback=feedback,
        ),
    )


@login_required
def it_export_notes_excel(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    try:
        from openpyxl import Workbook
    except ImportError:
        return HttpResponse("openpyxl doit etre installe pour exporter en Excel.", status=500)
    selection = _resolve_workflow_selection(request)
    academic_class = selection["selected_class"]
    selected_semester = selection["selected_semester"]
    if academic_class is None:
        return HttpResponseForbidden("Classe obligatoire.")

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Notes classe"
    sheet.append(["Classe", "Semestre", "Etudiant", "EC", "Coefficient", "Credits", "Session normale", "Rattrapage", "Note finale", "Valide"])
    grades = grade_entries_for_class(academic_class=academic_class)
    if selected_semester:
        grades = grades.filter(ec__ue__semester=selected_semester)
    for grade in grades.order_by("enrollment__student__username", "ec__ue__semester__number", "ec__title"):
        sheet.append([
            academic_class.display_name,
            f"S{grade.ec.ue.semester.number}",
            grade.enrollment.student.get_full_name() or grade.enrollment.student.username,
            grade.ec.title,
            grade.ec.coefficient,
            grade.ec.credit_required,
            grade.normal_score,
            grade.retake_score,
            grade.final_score,
            "oui" if grade.is_validated else "non",
        ])

    anomalies = workbook.create_sheet("Anomalies")
    anomalies.append(["Type", "Detail", "Action attendue"])
    state = get_notes_state(academic_class=academic_class, semester=selected_semester) if selected_semester else None
    if state:
        for alert in state.technical_alerts:
            anomalies.append(["Notes", alert, "Completer la grille puis verifier"])
    if anomalies.max_row == 1:
        anomalies.append(["Aucune", "Aucune anomalie bloquante detectee dans la selection.", "-"])

    results = workbook.create_sheet("Resultats")
    results.append(["Etudiant", "Semestre", "Moyenne", "Pourcentage", "Credits obtenus", "Credits requis", "Statut"])
    if selected_semester:
        enrollments = academic_class.enrollments.filter(is_active=True, academic_year=academic_class.academic_year).select_related("student")
        for enrollment in enrollments:
            summary = compute_semester_result(selected_semester, enrollment)
            results.append([
                enrollment.student.get_full_name() or enrollment.student.username,
                f"S{selected_semester.number}",
                summary["average"],
                summary["percentage"],
                summary["credit_obtained"],
                summary["credit_required"],
                state.label if state else "",
            ])

    for worksheet in workbook.worksheets:
        for column in ("A", "B", "C", "D"):
            worksheet.column_dimensions[column].width = 28
    for column in ("A", "B", "C"):
        sheet.column_dimensions[column].width = 28
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="notes-classe-{academic_class.id}.xlsx"'
    log_support_action(
        actor=request.user,
        branch=get_user_branch(request.user),
        action_type=SupportAuditLog.ACTION_EXCEL_EXPORTED,
        target_label=f"Export notes {academic_class.display_name}",
        details=f"Export Excel {'S' + str(selected_semester.number) if selected_semester else 'classe complete'}.",
    )
    return response


@login_required
def it_structure_workspace(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    selected_class_id = (request.GET.get("class_id") or request.GET.get("classe") or "").strip()
    student_query = (request.GET.get("student_q") or "").strip()
    section = (request.GET.get("section") or "classes").strip()
    return render(
        request,
        "portal/informaticien/workflows/structure_workspace.html",
        build_academic_structure_context(
            branch=get_user_branch(request.user),
            selected_class_id=selected_class_id,
            student_query=student_query,
            section=section,
        ),
    )


@login_required
def it_structure_modal(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    branch = get_user_branch(request.user)
    kind = (request.GET.get("kind") or "").strip()
    object_id = (request.GET.get("id") or "").strip()
    class_id = (request.GET.get("class_id") or "").strip()
    section = (request.GET.get("section") or "classes").strip()
    semester_id = (request.GET.get("semester_id") or "").strip()
    ue_id = (request.GET.get("ue_id") or "").strip()
    student_id = (request.GET.get("student_id") or "").strip()

    context = build_academic_structure_context(branch=branch, selected_class_id=class_id, section=section)
    context.update(
        {
            "kind": kind,
            "target_id": object_id,
            "target_class": AcademicClass.objects.filter(pk=object_id, branch=branch).first() if kind == "class" and object_id else None,
            "target_ue": UE.objects.filter(pk=object_id, semester__academic_class__branch=branch).first() if kind == "ue" and object_id else None,
            "target_ec": EC.objects.filter(pk=object_id, ue__semester__academic_class__branch=branch).first() if kind == "ec" and object_id else None,
            "target_student": Student.objects.select_related("inscription__candidature").filter(
                pk=student_id,
                inscription__candidature__branch=branch,
            ).first() if kind == "assign" and student_id else None,
            "selected_semester": Semester.objects.filter(pk=semester_id, academic_class__branch=branch).first() if semester_id else None,
            "selected_ue": UE.objects.filter(pk=ue_id, semester__academic_class__branch=branch).first() if ue_id else None,
        }
    )
    return render(request, "portal/informaticien/workflows/structure_modal.html", context)


def _render_structure_modal_from_post(request, *, branch, message):
    action = (request.POST.get("action") or "").strip()
    section = (request.POST.get("section") or "classes").strip()
    kind = {
        "save_class": "class",
        "save_ue": "ue",
        "save_ec": "ec",
        "assign_student": "assign",
    }.get(action, "class")
    object_id = {
        "save_class": request.POST.get("class_id"),
        "save_ue": request.POST.get("ue_id"),
        "save_ec": request.POST.get("ec_id"),
    }.get(action)
    class_id = request.POST.get("selected_class_id") or request.POST.get("class_id")
    semester_id = request.POST.get("semester_id")
    ue_id = request.POST.get("ue_id")
    student_id = request.POST.get("student_id")

    context = build_academic_structure_context(branch=branch, selected_class_id=class_id, section=section)
    context.update(
        {
            "kind": kind,
            "target_id": object_id,
            "target_class": AcademicClass.objects.filter(pk=object_id, branch=branch).first() if kind == "class" and object_id else None,
            "target_ue": UE.objects.filter(pk=object_id, semester__academic_class__branch=branch).first() if kind == "ue" and object_id else None,
            "target_ec": EC.objects.filter(pk=object_id, ue__semester__academic_class__branch=branch).first() if kind == "ec" and object_id else None,
            "target_student": Student.objects.select_related("inscription__candidature").filter(
                pk=student_id,
                inscription__candidature__branch=branch,
            ).first() if kind == "assign" and student_id else None,
            "selected_semester": Semester.objects.filter(pk=semester_id, academic_class__branch=branch).first() if semester_id else None,
            "selected_ue": UE.objects.filter(pk=ue_id, semester__academic_class__branch=branch).first() if ue_id else None,
            "form_error": message,
            "form_values": request.POST,
        }
    )
    response = render(request, "portal/informaticien/workflows/structure_modal.html", context)
    response["HX-Retarget"] = "#it-modal-root"
    return response


@login_required
def it_structure_action(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    if request.method != "POST":
        return HttpResponseForbidden("Methode non autorisee.")

    branch = get_user_branch(request.user)
    selected_class_id = (request.POST.get("selected_class_id") or "").strip()
    action = (request.POST.get("action") or "").strip()
    section = (request.POST.get("section") or "classes").strip()
    toast = None
    try:
        if action == "save_class":
            academic_class = save_academic_class(
                branch=branch,
                class_id=(request.POST.get("class_id") or "").strip() or None,
                programme_id=request.POST.get("programme_id"),
                academic_year_id=request.POST.get("academic_year_id"),
                level=request.POST.get("level"),
                threshold=request.POST.get("validation_threshold"),
                actor=request.user,
            )
            selected_class_id = str(academic_class.id)
            section = "classes"
            toast = {"level": "success", "message": "Classe academique enregistree."}
        elif action == "archive_class":
            archive_academic_class(branch=branch, class_id=request.POST.get("class_id"))
            section = "classes"
            toast = {"level": "success", "message": "Classe archivee."}
        elif action == "save_ue":
            ue = save_ue(
                branch=branch,
                ue_id=(request.POST.get("ue_id") or "").strip() or None,
                semester_id=request.POST.get("semester_id"),
                code=request.POST.get("code"),
                title=request.POST.get("title"),
            )
            selected_class_id = str(ue.semester.academic_class_id)
            section = "maquettes"
            toast = {"level": "success", "message": "UE enregistree."}
        elif action == "save_ec":
            ec = save_ec(
                branch=branch,
                ec_id=(request.POST.get("ec_id") or "").strip() or None,
                ue_id=request.POST.get("ue_id"),
                title=request.POST.get("title"),
                coefficient=request.POST.get("coefficient"),
                credit_required=request.POST.get("credit_required"),
            )
            selected_class_id = str(ec.ue.semester.academic_class_id)
            section = "maquettes"
            toast = {"level": "success", "message": "EC enregistre."}
        elif action == "delete_ec":
            delete_ec(branch=branch, ec_id=request.POST.get("ec_id"))
            section = "maquettes"
            toast = {"level": "success", "message": "EC supprime."}
        elif action == "assign_student":
            enrollment = assign_student_to_class(
                branch=branch,
                student_id=request.POST.get("student_id"),
                class_id=request.POST.get("class_id"),
            )
            selected_class_id = str(enrollment.academic_class_id)
            section = "affectations"
            toast = {"level": "success", "message": "Etudiant affecte a la classe."}
        else:
            raise ValidationError("Action de parametrage inconnue.")
    except ValidationError as exc:
        return _render_structure_modal_from_post(
            request,
            branch=branch,
            message=" ".join(exc.messages),
        )

    context = build_academic_structure_context(
        branch=branch,
        selected_class_id=selected_class_id,
        student_query=(request.POST.get("student_q") or "").strip(),
        section=section,
    )
    context["toast"] = toast
    response = render(request, "portal/informaticien/workflows/structure_workspace.html", context)
    response["HX-Trigger"] = "it-modal-close"
    return response


@login_required
def it_archives_workspace(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    branch = get_user_branch(request.user)
    academic_year_id = (request.GET.get("academic_year_id") or "").strip()
    class_id = (request.GET.get("class_id") or "").strip()
    candidates = archive_candidates_for_branch(branch=branch)
    preview = None
    if academic_year_id or class_id:
        preview = preview_archive(
            branch=branch,
            academic_year_id=academic_year_id or None,
            class_id=class_id or None,
        )
    return render(
        request,
        "portal/informaticien/workflows/archive_workspace.html",
        {
            "branch": branch,
            "archive_batches": archive_batches_for_branch(branch=branch)[:40],
            "academic_years": candidates["academic_years"],
            "classes": candidates["classes"],
            "selected_academic_year_id": academic_year_id,
            "selected_class_id": class_id,
            "preview": preview,
            "toast": None,
        },
    )


@login_required
def it_archives_action(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    if request.method != "POST":
        return HttpResponseForbidden("Methode non autorisee.")
    branch = get_user_branch(request.user)
    action = (request.POST.get("action") or "").strip()
    toast = {"level": "success", "message": "Archive mise a jour."}
    try:
        if action == "archive_class":
            archive_class(
                branch=branch,
                class_id=request.POST.get("class_id"),
                actor=request.user,
                reason=request.POST.get("reason"),
            )
            toast = {"level": "success", "message": "Classe archivee avec succes."}
        elif action == "archive_year":
            archive_year(
                branch=branch,
                academic_year_id=request.POST.get("academic_year_id"),
                actor=request.user,
                reason=request.POST.get("reason"),
            )
            toast = {"level": "success", "message": "Annee academique archivee avec succes."}
        elif action == "restore":
            restore_archive_batch(
                branch=branch,
                batch_id=request.POST.get("batch_id"),
                actor=request.user,
            )
            toast = {"level": "success", "message": "Archive restauree."}
        else:
            raise ValidationError("Action d'archivage inconnue.")
    except ValidationError as exc:
        toast = {"level": "error", "message": " ".join(exc.messages)}

    candidates = archive_candidates_for_branch(branch=branch)
    return render(
        request,
        "portal/informaticien/workflows/archive_workspace.html",
        {
            "branch": branch,
            "archive_batches": archive_batches_for_branch(branch=branch)[:40],
            "academic_years": candidates["academic_years"],
            "classes": candidates["classes"],
            "selected_academic_year_id": "",
            "selected_class_id": "",
            "preview": None,
            "toast": toast,
        },
    )


@login_required
def it_archive_detail(request, batch_id):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    branch = get_user_branch(request.user)
    try:
        context = archive_detail(branch=branch, batch_id=batch_id)
    except ValidationError as exc:
        return HttpResponse(" ".join(exc.messages), status=404)
    return render(request, "portal/informaticien/workflows/archive_detail.html", context)


@login_required
def it_supervision_workspace(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    return render(
        request,
        "portal/informaticien/workflows/supervision_workspace.html",
        build_supervision_context(branch=get_user_branch(request.user)),
    )


@login_required
def it_catalog_workspace(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    return render(request, "portal/informaticien/workflows/catalog_workspace.html", build_catalog_context())


@login_required
def it_catalog_action(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    if request.method != "POST":
        return HttpResponseForbidden("Methode non autorisee.")
    toast = None
    try:
        create_catalog_item(
            kind=request.POST.get("kind"),
            name=request.POST.get("name"),
            code=request.POST.get("code"),
            description=request.POST.get("description"),
        )
        toast = {"level": "success", "message": "Element ajoute."}
    except ValidationError as exc:
        toast = {"level": "error", "message": " ".join(exc.messages)}
    return render(request, "portal/informaticien/workflows/catalog_workspace.html", build_catalog_context(toast=toast))


def _build_accounts_flow_context(request, *, toast=None):
    branch = get_user_branch(request.user)
    query = (request.GET.get("q") or "").strip()
    users_qs = get_scoped_staff_queryset(branch=branch).filter(profile__branch=branch) if branch else get_scoped_staff_queryset(branch=branch).none()
    if query:
        users_qs = users_qs.filter(
            Q(username__icontains=query)
            | Q(email__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )
    rows = []
    for user in users_qs.select_related("profile")[:40]:
        state = get_account_support_state(user)
        if state.is_suspended:
            account_state = "suspendu"
        elif state.is_blocked:
            account_state = "bloque"
        elif user.is_active:
            account_state = "actif"
        else:
            account_state = "inactif"
        rows.append({"user": user, "support_state": state, "account_state": account_state})

    return {
        "branch": branch,
        "query": query,
        "rows": rows,
        "toast": toast,
    }


@login_required
def it_accounts_flow_workspace(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    return render(
        request,
        "portal/informaticien/workflows/accounts_workspace.html",
        _build_accounts_flow_context(request),
    )


@login_required
def it_accounts_flow_action(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    if request.method != "POST":
        return HttpResponseForbidden("Methode non autorisee.")

    branch = get_user_branch(request.user)
    target_user = get_object_or_404(
        get_scoped_staff_queryset(branch=branch).filter(profile__branch=branch),
        pk=request.POST.get("target_user_id"),
    )
    if not _same_branch_or_forbidden(request=request, target_user=target_user):
        return HttpResponseForbidden("Action hors annexe refusee.")
    action = (request.POST.get("action") or "").strip()
    toast = None

    if action == "toggle_active":
        target_user.is_active = not target_user.is_active
        target_user.save(update_fields=["is_active"])
        log_support_action(
            actor=request.user,
            branch=branch,
            action_type="account_activated" if target_user.is_active else "account_deactivated",
            target_user=target_user,
            target_label=target_user.get_full_name() or target_user.username,
            details="Action depuis workflow comptes informaticien.",
        )
        toast = {"level": "success", "message": "Etat du compte mis a jour."}
    elif action == "reset_password":
        temp_password = create_temp_password()
        target_user.set_password(temp_password)
        target_user.save(update_fields=["password"])
        log_support_action(
            actor=request.user,
            branch=branch,
            action_type="password_reset",
            target_user=target_user,
            target_label=target_user.get_full_name() or target_user.username,
            details="Reset mot de passe depuis workflow comptes informaticien.",
        )
        toast = {"level": "success", "message": f"Mot de passe temporaire: {temp_password}"}
    else:
        toast = {"level": "error", "message": "Action compte inconnue."}

    return render(
        request,
        "portal/informaticien/workflows/accounts_workspace.html",
        _build_accounts_flow_context(request, toast=toast),
    )


@login_required
def it_user_modal(request, user_id):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")

    branch = get_user_branch(request.user)
    target_user = get_object_or_404(
        get_scoped_staff_queryset(branch=branch).filter(profile__branch=branch).select_related("profile"),
        pk=user_id,
    )
    if not _same_branch_or_forbidden(request=request, target_user=target_user):
        return HttpResponseForbidden("Action hors annexe refusee.")
    return render(
        request,
        "portal/informaticien/workflows/user_modal.html",
        {
            "target_user": target_user,
            "profile": target_user.profile,
        },
    )


@login_required
def it_user_modal_save(request, user_id):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    if request.method != "POST":
        return HttpResponseForbidden("Methode non autorisee.")

    branch = get_user_branch(request.user)
    target_user = get_object_or_404(
        get_scoped_staff_queryset(branch=branch).filter(profile__branch=branch).select_related("profile"),
        pk=user_id,
    )
    if not _same_branch_or_forbidden(request=request, target_user=target_user):
        return HttpResponseForbidden("Action hors annexe refusee.")
    profile = target_user.profile

    target_user.first_name = (request.POST.get("first_name") or "").strip()
    target_user.last_name = (request.POST.get("last_name") or "").strip()
    target_user.email = (request.POST.get("email") or "").strip().lower()
    target_user.is_active = bool(request.POST.get("is_active"))
    target_user.save(update_fields=["first_name", "last_name", "email", "is_active"])

    log_support_action(
        actor=request.user,
        branch=branch,
        action_type="email_updated",
        target_user=target_user,
        target_label=target_user.get_full_name() or target_user.username,
        details="Modification utilisateur depuis modal informaticien.",
    )

    return render(
        request,
        "portal/informaticien/workflows/user_modal.html",
        {
            "target_user": target_user,
            "profile": profile,
            "toast": {"level": "success", "message": "Utilisateur mis a jour."},
        },
    )


@login_required
def it_branch_settings_workspace(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    branch = get_user_branch(request.user)
    settings = get_branch_settings(branch=branch)
    return render(
        request,
        "portal/informaticien/workflows/branch_settings_workspace.html",
        {
            "branch": branch,
            "settings": settings,
            "profile": getattr(request.user, "profile", None),
        },
    )


@login_required
def it_branch_settings_save(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    if request.method != "POST":
        return HttpResponseForbidden("Methode non autorisee.")
    branch = get_user_branch(request.user)
    toast = None
    try:
        settings = update_branch_settings(
            actor=request.user,
            branch=branch,
            validation_threshold=request.POST.get("validation_threshold"),
            active_academic_year=request.POST.get("active_academic_year"),
            local_config=request.POST.get("local_config"),
        )
        toast = {"level": "success", "message": "Parametres mis a jour."}
    except ValidationError as exc:
        settings = get_branch_settings(branch=branch)
        toast = {"level": "error", "message": " ".join(exc.messages)}
    return render(
        request,
        "portal/informaticien/workflows/branch_settings_workspace.html",
        {
            "branch": branch,
            "settings": settings,
            "toast": toast,
            "profile": getattr(request.user, "profile", None),
        },
    )


@login_required
def it_notes_retake_modal(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")

    return render(
        request,
        "portal/informaticien/workflows/retake_modal.html",
        _build_retake_modal_context(request),
    )


@login_required
def it_my_account_workspace(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    profile = getattr(request.user, "profile", None)
    return render(
        request,
        "portal/informaticien/workflows/my_account_workspace.html",
        {
            "profile": profile,
        },
    )


@login_required
def it_my_account_save(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    if request.method != "POST":
        return HttpResponseForbidden("Methode non autorisee.")
    request.user.first_name = (request.POST.get("first_name") or "").strip()
    request.user.last_name = (request.POST.get("last_name") or "").strip()
    request.user.email = (request.POST.get("email") or "").strip().lower()
    request.user.save(update_fields=["first_name", "last_name", "email"])
    if request.POST.get("return_settings"):
        branch = get_user_branch(request.user)
        return render(
            request,
            "portal/informaticien/workflows/branch_settings_workspace.html",
            {
                "branch": branch,
                "settings": get_branch_settings(branch=branch),
                "profile": getattr(request.user, "profile", None),
                "toast": {"level": "success", "message": "Profil mis a jour."},
            },
        )
    return render(
        request,
        "portal/informaticien/workflows/my_account_workspace.html",
        {
            "profile": getattr(request.user, "profile", None),
            "toast": {"level": "success", "message": "Profil mis a jour."},
        },
    )


@login_required
def it_student_card_pdf(request, student_id):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")

    branch = get_user_branch(request.user)
    student_qs = Student.objects.select_related(
        "inscription__candidature__branch",
        "inscription__candidature__programme",
    )
    if branch:
        student_qs = student_qs.filter(inscription__candidature__branch=branch)
    student = get_object_or_404(student_qs, pk=student_id)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=landscape((86 * mm, 54 * mm)))
    _draw_student_card(pdf, student=student)
    pdf.save()
    buffer.seek(0)
    log_support_action(
        actor=request.user,
        branch=branch,
        action_type=SupportAuditLog.ACTION_STUDENT_CARD_GENERATED,
        target_user=student.user,
        target_label=f"Carte {student.matricule or student.id}",
        details="Carte individuelle generee depuis le dashboard informaticien.",
    )
    return FileResponse(
        buffer,
        as_attachment=request.GET.get("preview") != "1",
        filename=f"carte-{student.matricule or student.id}.pdf",
    )


@login_required
def it_class_cards_pdf(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    branch = get_user_branch(request.user)
    selection = _resolve_workflow_selection(request)
    academic_class = selection["selected_class"]
    if academic_class is None or academic_class.branch_id != branch.id:
        return HttpResponseForbidden("Classe hors annexe refusee.")

    students = get_it_students_for_class(academic_class=academic_class)
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=landscape((86 * mm, 54 * mm)))
    for student in students:
        _draw_student_card(pdf, student=student, academic_class=academic_class)
    pdf.save()
    buffer.seek(0)
    log_support_action(
        actor=request.user,
        branch=branch,
        action_type=SupportAuditLog.ACTION_STUDENT_CARD_GENERATED,
        target_label=f"Cartes classe {academic_class.display_name}",
        details=f"{students.count()} carte(s) generee(s).",
    )
    return FileResponse(
        buffer,
        as_attachment=request.GET.get("preview") != "1",
        filename=f"cartes-classe-{academic_class.id}.pdf",
    )


def _draw_student_card(pdf, *, student, academic_class=None):
    page_size = landscape((86 * mm, 54 * mm))
    width, height = page_size
    candidature = student.inscription.candidature
    enrollment = (
        student.user.academic_enrollments.select_related("academic_class", "academic_year")
        .filter(is_active=True)
        .order_by("-created_at")
        .first()
    )
    academic_class = academic_class or (enrollment.academic_class if enrollment else None)
    academic_year = academic_class.academic_year if academic_class else getattr(enrollment, "academic_year", None)
    qr_value = f"ESFE:{student.matricule}:{student.id}"

    pdf.setPageSize(page_size)
    pdf.setFillColor(colors.HexColor("#f8fafc"))
    pdf.rect(0, 0, width, height, stroke=0, fill=1)
    pdf.setFillColor(colors.HexColor("#082f49"))
    pdf.rect(0, height - 15 * mm, width, 15 * mm, stroke=0, fill=1)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(5 * mm, height - 8 * mm, "ESFE")
    pdf.setFont("Helvetica", 7)
    pdf.drawString(20 * mm, height - 7 * mm, "Ecole Superieure de Formation et d'Excellence")
    pdf.drawString(20 * mm, height - 11 * mm, f"Annexe: {candidature.branch.name[:36]}")

    pdf.setStrokeColor(colors.HexColor("#cbd5e1"))
    pdf.setFillColor(colors.white)
    pdf.roundRect(5 * mm, height - 39 * mm, 20 * mm, 22 * mm, 3 * mm, stroke=1, fill=1)
    pdf.setFillColor(colors.HexColor("#64748b"))
    pdf.setFont("Helvetica-Bold", 7)
    pdf.drawCentredString(15 * mm, height - 29 * mm, "PHOTO")

    pdf.setFillColor(colors.HexColor("#0f172a"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(28 * mm, height - 21 * mm, student.full_name[:36])
    pdf.setFont("Helvetica", 7.5)
    pdf.drawString(28 * mm, height - 27 * mm, f"Matricule: {student.matricule or '-'}")
    pdf.drawString(28 * mm, height - 32 * mm, f"Classe: {(academic_class.display_name if academic_class else '-')[:34]}")
    pdf.drawString(28 * mm, height - 37 * mm, f"Formation: {candidature.programme.title[:32]}")
    pdf.drawString(28 * mm, height - 42 * mm, f"Annee: {academic_year or '-'}")

    try:
        import qrcode
        qr_image = qrcode.make(qr_value)
        qr_buffer = BytesIO()
        qr_image.save(qr_buffer, format="PNG")
        qr_buffer.seek(0)
        pdf.drawImage(ImageReader(qr_buffer), width - 20 * mm, 20 * mm, 14 * mm, 14 * mm)
    except Exception:
        pdf.setFont("Helvetica", 6)
        pdf.drawRightString(width - 5 * mm, 25 * mm, qr_value[:22])

    pdf.setFillColor(colors.HexColor("#e2e8f0"))
    pdf.rect(0, 0, width, 7 * mm, stroke=0, fill=1)
    pdf.setFillColor(colors.HexColor("#334155"))
    pdf.setFont("Helvetica", 6.5)
    pdf.drawString(5 * mm, 2.5 * mm, "Carte personnelle - emission automatique dashboard informaticien")
    pdf.showPage()

    pdf.setPageSize(page_size)
    pdf.setFillColor(colors.white)
    pdf.rect(0, 0, width, height, stroke=0, fill=1)
    pdf.setFillColor(colors.HexColor("#082f49"))
    pdf.rect(0, height - 10 * mm, width, 10 * mm, stroke=0, fill=1)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(5 * mm, height - 6.5 * mm, "Informations utiles")
    pdf.setFillColor(colors.HexColor("#0f172a"))
    pdf.setFont("Helvetica", 7)
    lines = [
        "Cette carte doit etre presentee a toute demande de l'administration.",
        "En cas de perte, contacter immediatement le service scolarite.",
        f"Contact annexe: {candidature.branch.phone or candidature.branch.email or '-'}",
        f"Code unique: {qr_value}",
    ]
    y = height - 18 * mm
    for line in lines:
        pdf.drawString(6 * mm, y, line[:78])
        y -= 5 * mm
    pdf.line(width - 35 * mm, 13 * mm, width - 6 * mm, 13 * mm)
    pdf.setFont("Helvetica-Bold", 7)
    pdf.drawCentredString(width - 20 * mm, 8 * mm, "Signature / cachet")
    pdf.showPage()
