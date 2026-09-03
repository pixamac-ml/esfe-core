from __future__ import annotations

from io import BytesIO
from urllib.parse import urlencode
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Count, Q
from django.http import FileResponse, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from academics.imports.template_service import generate_notes_workbook
from academics.models import AcademicClass, AcademicYear, EC, ECGrade, Semester, UE
from academics.selectors.programme_structure_selectors import semester_has_active_ecs
from accounts.models import AccountSecurityEvent, AccountSessionRecord, CartePersonnel
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
    ACTION_ACTIVATE_RETAKE,
    ACTION_PUBLISH_NORMAL,
    ACTION_SUBMIT_TO_DIRECTOR,
    apply_notes_workflow_action,
    get_available_actions,
    get_notes_state,
    get_retake_candidates,
)
from portal.services.it_support_service import (
    can_manage_user_in_branch,
    get_account_support_state,
    get_scoped_staff_queryset,
    get_scoped_student_queryset,
    reactivate_account,
    unblock_account,
)
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
from portal.selectors.informaticien import support_tickets_for_branch
from portal.models import SupportAuditLog, SupportTicket
from students.models import CarteEtudiant, Student, VerificationLog
from portal.views.admin_grades import _build_notes_grid_context
from notifier.models import NotificationMessage


def _require_it_support(request):
    if get_user_position(request.user) != "it_support":
        return False
    if get_user_branch(request.user) is None:
        return False
    return True


@login_required
def it_restricted_workspace(request, *args, **kwargs):
    """Ferme les anciennes URLs de gouvernance, sans détruire leurs briques."""
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    return HttpResponseForbidden(
        "Cette fonction ne fait plus partie du perimetre de l'informaticien. "
        "Elle est reservee au role academique ou de direction competent."
    )


def _render_it_section(request, module_key, template_name, context):
    """
    Rend le fragment d'une section du dashboard informaticien.

    Si la requete vient de HTMX (navigation interne), seul le fragment est
    renvoye. Sinon (navigation directe, F5, retour/avance navigateur), la
    coquille complete du dashboard est reconstruite avec ce meme fragment
    deja insere dans #it-dashboard-workspace, pour eviter une page cassee.
    """
    if getattr(request, "htmx", False):
        return render(request, template_name, context)
    fragment = render(request, template_name, context)
    from portal.views.views import _render_it_dashboard
    return _render_it_dashboard(
        request,
        initial_module=module_key,
        initial_workspace_html=fragment.content.decode(fragment.charset or "utf-8"),
    )


def _it_subnavigation(*, url_name, active, definitions, query=None):
    """Build the same HTMX-backed secondary navigation contract as DE."""

    endpoint = reverse(url_name)
    query = dict(query or {})
    items = []
    for item_id, label, icon, extra_query in definitions:
        params = {**query, **extra_query}
        encoded = urlencode(params)
        url = f"{endpoint}?{encoded}" if encoded else endpoint
        items.append(
            {
                "id": item_id,
                "label": label,
                "icon": icon,
                "href": url,
                "hx_get": url,
                "hx_target": "#it-dashboard-workspace",
                "hx_swap": "innerHTML",
                "hx_push_url": url,
                "hx_indicator": "#it-dashboard-loading",
                "hx_sync": "#it-dashboard-workspace:replace",
            }
        )
    return items


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
            "actions": get_available_actions(state=state, audience="it_support"),
            "academic_template_ready": bool(
                context["selected_semester"]
                and semester_has_active_ecs(context["selected_semester"])
            ),
            "toast": toast,
        }
    )
    return context


@login_required
def it_notes_kpi(request):
    if get_user_position(request.user) != "it_support":
        return HttpResponseForbidden("Acces refuse.")

    from academics.models import AcademicEnrollment, ECGrade, AcademicDebt

    from portal.services.notes_workflow import get_notes_state

    branch = get_user_branch(request.user)
    classes_qs = get_it_academic_classes(branch=branch)

    class_id = (request.GET.get("class_id") or "").strip()
    semester_id = (request.GET.get("semester_id") or "").strip()

    academic_class = get_object_or_404(classes_qs, pk=int(class_id)) if class_id.isdigit() else None
    semester = (
        get_object_or_404(
            Semester.objects.select_related("academic_class"),
            pk=int(semester_id),
            academic_class=academic_class,
        )
        if semester_id.isdigit() and academic_class
        else None
    )

    if not academic_class or not semester:
        return HttpResponse("Selection invalide", status=400)

    enrollments = AcademicEnrollment.objects.filter(
        academic_class=academic_class,
        academic_year=academic_class.academic_year,
        is_active=True,
    )
    enrollment_count = enrollments.count()

    ec_count = semester.ues.aggregate(total=Count("ecs", distinct=True))["total"] or 0
    expected_grades = enrollment_count * ec_count

    grade_stats = ECGrade.objects.filter(
        enrollment__in=enrollments,
        ec__ue__semester=semester,
    ).aggregate(
        entered_grades=Count("id", filter=Q(normal_score__isnull=False)),
        validated_grades=Count("id", filter=Q(is_validated=True)),
        failed_grades=Count("id", filter=Q(final_score__isnull=False, is_validated=False)),
    )
    entered_grades = grade_stats["entered_grades"]
    validated_grades = grade_stats["validated_grades"]
    failed_grades = grade_stats["failed_grades"]

    pending_debts = AcademicDebt.objects.filter(
        academic_class=academic_class,
        semester=semester,
        status="pending",
    ).count()

    progress = int((entered_grades / expected_grades) * 100) if expected_grades else 0

    state = get_notes_state(academic_class=academic_class, semester=semester)

    context = {
        "enrollment_count": enrollment_count,
        "entered_grades": entered_grades,
        "expected_grades": expected_grades,
        "validated_grades": validated_grades,
        "failed_grades": failed_grades,
        "pending_debts": pending_debts,
        "progress": min(progress, 100),
        "state_code": state.code if state else "empty",
        "state_label": state.label if state else "Non commence",
        "ec_count": ec_count,
        "class_id": class_id,
        "semester_id": semester_id,
    }

    return render(request, "portal/informaticien/partials/notes_kpi.html", context)


@login_required
def it_workflow_section(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    context = _build_notes_workflow_context(request)
    academic_class = context.get("selected_class")
    semester = context.get("selected_semester")
    state = context.get("state")
    if not academic_class or not semester or state is None:
        return HttpResponse("Selection invalide", status=400)
    from ui.components.notes.notes_workflow_bar import build_workflow_bar_data
    has_candidates = bool(state.retake_candidates_count) if state else None
    workflow_bar = build_workflow_bar_data(state.code, has_candidates=has_candidates)
    return render(request, "notes/notes_workflow_section.html", {
        "academic_class": academic_class,
        "semester": semester,
        "state": state,
        "actions": context.get("actions", []),
        "workflow_bar": workflow_bar,
        "drawer_mode": bool(request.GET.get("drawer")),
    })


@login_required
def it_notes_decisions(request):
    if get_user_position(request.user) != "it_support":
        return HttpResponseForbidden("Acces refuse.")

    from portal.selectors import get_it_academic_classes
    from academics.models import AcademicEnrollment, AcademicDebt
    from academics.services.year import (
        DECISION_ADMISSIBLE,
        DECISION_NON_ADMIS,
        DECISION_VALIDE,
        compute_annual_decision,
    )

    branch = get_user_branch(request.user)
    classes_qs = get_it_academic_classes(branch=branch)

    class_id = (request.GET.get("class_id") or "").strip()

    academic_class = get_object_or_404(classes_qs, pk=int(class_id)) if class_id.isdigit() else None

    if not academic_class:
        return HttpResponse("", status=200)

    enrollments = AcademicEnrollment.objects.filter(
        academic_class=academic_class,
        academic_year=academic_class.academic_year,
        is_active=True,
    ).select_related("student__student_profile__inscription__candidature")

    decision_labels = {
        DECISION_VALIDE: "VALIDÉ",
        DECISION_ADMISSIBLE: "ADMISSIBLE",
        DECISION_NON_ADMIS: "NON ADMIS",
    }

    decisions = []
    for enrollment in enrollments:
        result = compute_annual_decision(enrollment)
        semester_validated = {
            sr["semester"]: sr.get("is_validated")
            for sr in result.get("semester_results", [])
        }

        def _semester_label(key):
            validated = semester_validated.get(key)
            if validated is None:
                return "—"
            return "VALIDÉ" if validated else "NON ADMIS"

        active_debts = AcademicDebt.objects.filter(
            enrollment=enrollment,
            status="pending",
        ).select_related("ec")

        debt_names = [f"{d.ec.title} (S{d.semester.number})" for d in active_debts]

        decisions.append({
            "student_name": enrollment.student.student_profile.full_name,
            "s1": _semester_label("S1"),
            "s2": _semester_label("S2"),
            "year": decision_labels.get(result["decision"], result["decision"]),
            "debts": debt_names,
        })

    active_debts_count = AcademicDebt.objects.filter(
        academic_class=academic_class,
        status="pending",
    ).count()

    return render(request, "portal/informaticien/partials/notes_decisions.html", {
        "decisions": decisions,
        "debts_count": active_debts_count,
    })


@login_required
def it_notes_flow_workspace(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    context = _build_notes_workflow_context(request)
    if request.GET.get("drawer") == "1":
        return render(
            request,
            "portal/informaticien/drawers/notes_drawer.html",
            context,
        )
    return _render_it_section(
        request,
        "notes",
        "portal/informaticien/workflows/notes_workspace.html",
        context,
    )


@login_required
def it_home_workspace(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    return _render_it_section(
        request,
        "home",
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
        if action not in {
            "start_saisie",
            "continue_saisie",
            "verifier_notes",
            ACTION_PUBLISH_NORMAL,
            ACTION_ACTIVATE_RETAKE,
            ACTION_SUBMIT_TO_DIRECTOR,
        }:
            return HttpResponseForbidden(
                "La validation officielle et la publication des resultats relevent du Directeur des etudes."
            )
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
            ACTION_SUBMIT_TO_DIRECTOR: "Session technique cloturee et transmise au Directeur des etudes.",
            "publier_resultats_finaux": "Resultats finaux publies. Les releves et exports sont deblocables.",
            "generer_decisions_annuelles": "Decisions annuelles generees avec bulletins.",
            "generer_bulletins": "Bulletins semestriels generes.",
        }
        toast = {"level": "success", "message": messages.get(action, "Workflow notes mis a jour.")}
    except ValidationError as exc:
        if request.POST.get("from_modal") == "retake":
            modal_context = _build_retake_modal_context(request)
            modal_context["form_error"] = " ".join(exc.messages)
            response = render(request, "portal/informaticien/workflows/retake_modal.html", modal_context)
            response["HX-Retarget"] = "#it-dashboard-modal-content"
            return response
        toast = {"level": "error", "message": " ".join(exc.messages)}

    template_name = (
        "portal/informaticien/drawers/notes_drawer.html"
        if request.POST.get("drawer") == "1"
        else "portal/informaticien/workflows/notes_workspace.html"
    )
    response = render(
        request,
        template_name,
        _build_notes_workflow_context(request, toast=toast),
    )
    if successful:
        response["HX-Trigger"] = '{"it-modal-close": "", "kpi-update": "", "workflow-update": ""}'
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
    if not semester_has_active_ecs(semester):
        return HttpResponse(
            '<div class="workflow-grid-placeholder">Cette maquette doit etre completee par le Directeur des etudes avant la saisie des notes.</div>',
            status=409,
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
        "portal/admin/grades/partials/notes_maquette.html",
        {
            **grid_context,
            "embedded_in_dashboard": True,
        },
    )


def _build_cards_workspace_context(request):
    selection = _resolve_workflow_selection(request)
    branch = selection["branch"]
    cards_view = (request.GET.get("view") or "issue").strip()
    if cards_view not in {"issue", "students", "staff", "verifications"}:
        cards_view = "issue"
    search = (request.GET.get("q") or "").strip()
    students = []
    if selection["selected_class"]:
        students = list(get_it_students_for_class(academic_class=selection["selected_class"])[:80])
    staff = list(
        get_scoped_staff_queryset(branch=branch)
        .filter(profile__employment_status="active")[:100]
    )
    common_query = {}
    if selection["selected_class"]:
        common_query["class_id"] = selection["selected_class"].id
    selection.update({
        "students": students,
        "staff": staff,
        "workflow_module": "cards",
        "cards_view": cards_view,
        "cards_subnavigation": _it_subnavigation(
            url_name="accounts_portal:it_cards_workspace",
            active=cards_view,
            query=common_query,
            definitions=(
                ("issue", "Émission", "badge", {"view": "issue"}),
                ("students", "Suivi étudiants", "graduation-cap", {"view": "students"}),
                ("staff", "Suivi personnel", "contact", {"view": "staff"}),
                ("verifications", "Vérifications QR", "scan-line", {"view": "verifications"}),
            ),
        ),
        "card_search": search,
    })

    if cards_view == "students":
        cards = CarteEtudiant.objects.select_related(
            "etudiant__inscription__candidature",
        ).filter(etudiant__inscription__candidature__branch=branch)
        if selection["selected_class"]:
            cards = cards.filter(
                etudiant__user__academic_enrollments__academic_class=selection["selected_class"],
                etudiant__user__academic_enrollments__is_active=True,
            )
        if search:
            cards = cards.filter(
                Q(etudiant__matricule__icontains=search)
                | Q(etudiant__inscription__candidature__first_name__icontains=search)
                | Q(etudiant__inscription__candidature__last_name__icontains=search)
            )
        selection["student_cards"] = list(cards.distinct().order_by("-date_emission")[:200])
    elif cards_view == "staff":
        cards = CartePersonnel.objects.select_related("profile__user").filter(
            code_annexe=getattr(branch, "code", ""),
        )
        if search:
            cards = cards.filter(
                Q(profile__employee_code__icontains=search)
                | Q(profile__user__first_name__icontains=search)
                | Q(profile__user__last_name__icontains=search)
                | Q(profile__user__username__icontains=search)
            )
        selection["staff_cards"] = list(cards.order_by("-date_emission")[:200])
    elif cards_view == "verifications":
        card_logs = VerificationLog.objects.select_related(
            "carte__etudiant__inscription__candidature",
            "staff_card__profile__user",
        ).filter(
            Q(carte__etudiant__inscription__candidature__branch=branch)
            | Q(staff_card__code_annexe=getattr(branch, "code", "")),
        )
        selection["card_verifications"] = list(card_logs.order_by("-created_at")[:200])
    return selection


@login_required
def it_cards_workspace(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")

    selection = _build_cards_workspace_context(request)
    return _render_it_section(request, "cards", "portal/informaticien/workflows/cards_workspace.html", selection)


@login_required
def it_card_status_action(request):
    if not _require_it_support(request) or request.method != "POST":
        return HttpResponseForbidden("Acces refuse.")
    branch = get_user_branch(request.user)
    scope = (request.POST.get("scope") or "").strip()
    action = (request.POST.get("action") or "").strip()
    card_id = (request.POST.get("card_id") or "").strip()
    if not card_id.isdigit() or scope not in {"student", "staff"}:
        return HttpResponse("Demande de carte invalide.", status=400)

    if scope == "student":
        card = get_object_or_404(
            CarteEtudiant.objects.select_related("etudiant__user", "etudiant__inscription__candidature"),
            pk=int(card_id),
            etudiant__inscription__candidature__branch=branch,
        )
        target_user = card.etudiant.user
        label = f"Carte étudiant {card.etudiant.matricule}"
        view_name = "students"
    else:
        card = get_object_or_404(
            CartePersonnel.objects.select_related("profile__user"),
            pk=int(card_id),
            code_annexe=getattr(branch, "code", ""),
        )
        target_user = card.profile.user
        label = f"Carte personnel {card.profile.employee_code or target_user.id}"
        view_name = "staff"

    if action == "lost":
        card.statut = "perdue"
        card.save(update_fields=["statut"])
        detail = "Carte declaree perdue."
    elif action == "revoke":
        card.statut = "revoquee"
        card.save(update_fields=["statut"])
        detail = "Carte revoquee."
    elif action == "reissue":
        card.public_reference = uuid4()
        card.statut = "active"
        if scope == "student":
            card.token_version = "v2"
        card.date_expiration = _card_expiration_date()
        update_fields = ["public_reference", "statut", "date_expiration"]
        if scope == "student":
            update_fields.append("token_version")
        card.save(update_fields=update_fields)
        detail = "Carte reemise : l'ancien QR est invalide et le nouveau PDF doit etre imprime."
    else:
        return HttpResponse("Action de carte invalide.", status=400)

    log_support_action(
        actor=request.user,
        branch=branch,
        action_type=SupportAuditLog.ACTION_STUDENT_CARD_GENERATED,
        target_user=target_user,
        target_label=label,
        details=detail,
    )
    request.GET = request.GET.copy()
    request.GET["view"] = view_name
    return it_cards_workspace(request)


@login_required
def it_support_flow_workspace(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    branch = get_user_branch(request.user)
    status = (request.GET.get("status") or "").strip()
    context = build_support_context(branch=branch, status=status, page=request.GET.get("page"))
    context["support_subnavigation"] = _it_subnavigation(
        url_name="accounts_portal:it_support_flow_workspace",
        active=status or "all",
        definitions=(
            ("all", "Tous", "layout-list", {"status": ""}),
            ("open", "Ouverts", "circle-dot", {"status": SupportTicket.STATUS_OPEN}),
            ("in_progress", "En cours", "loader-circle", {"status": SupportTicket.STATUS_IN_PROGRESS}),
            ("resolved", "Résolus", "circle-check", {"status": SupportTicket.STATUS_RESOLVED}),
        ),
    )
    return _render_it_section(
        request,
        "support",
        "portal/informaticien/workflows/support_workspace.html",
        context,
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
        {
            **build_support_context(branch=branch, status=request.POST.get("status", ""), toast=toast),
            "support_subnavigation": _it_subnavigation(
                url_name="accounts_portal:it_support_flow_workspace",
                active=request.POST.get("status", "") or "all",
                definitions=(
                    ("all", "Tous", "layout-list", {"status": ""}),
                    ("open", "Ouverts", "circle-dot", {"status": SupportTicket.STATUS_OPEN}),
                    ("in_progress", "En cours", "loader-circle", {"status": SupportTicket.STATUS_IN_PROGRESS}),
                    ("resolved", "Résolus", "circle-check", {"status": SupportTicket.STATUS_RESOLVED}),
                ),
            ),
        },
    )


@login_required
def it_audit_workspace(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    return _render_it_section(
        request,
        "audit",
        "portal/informaticien/workflows/audit_workspace.html",
        build_audit_context(
            branch=get_user_branch(request.user),
            page=request.GET.get("page"),
            query=(request.GET.get("q") or "").strip(),
            action_type=(request.GET.get("action_type") or "").strip(),
        ),
    )


def _resolve_import_selection(request):
    selection = _resolve_workflow_selection(request)
    return selection["classes"], selection["selected_class"], selection["selected_semester"]


def _paginate_items(items, page_number, *, per_page):
    paginator = Paginator(items, per_page)
    try:
        return paginator.page(page_number or 1)
    except (EmptyPage, PageNotAnInteger):
        return paginator.page(1)


def _build_structure_drawer_context(*, branch, class_id="", semester_id="", ue_id="", ec_id="", section="maquettes", ue_page=1, ec_page=1, ec_ue_id=""):
    actual_class = (
        AcademicClass.objects.select_related("programme", "academic_year", "branch")
        .filter(pk=class_id, branch=branch, is_archived=False)
        .first()
        if class_id
        else None
    )
    context = build_academic_structure_context(
        branch=branch,
        selected_class_id=actual_class.id if actual_class else None,
        section=section,
    )
    selected_class = actual_class
    context["selected_class"] = selected_class
    selected_semester = None
    selected_ue = None
    selected_ec = None

    if selected_class is not None and semester_id:
        selected_semester = Semester.objects.filter(
            pk=semester_id,
            academic_class__branch=branch,
            academic_class=selected_class,
        ).first()
    elif selected_class is not None:
        selected_semester = selected_class.semesters.order_by("number").first()

    if ue_id:
        selected_ue = UE.objects.filter(
            pk=ue_id,
            semester__academic_class__branch=branch,
        ).select_related("semester", "semester__academic_class").first()

    if ec_id:
        selected_ec = EC.objects.filter(
            pk=ec_id,
            ue__semester__academic_class__branch=branch,
        ).select_related("ue", "ue__semester", "ue__semester__academic_class").first()

    if selected_ec is not None and selected_ue is None:
        selected_ue = selected_ec.ue
    if selected_ue is not None and selected_semester is None:
        selected_semester = selected_ue.semester

    semesters = list(selected_class.semesters.prefetch_related("ues__ecs").order_by("number")) if selected_class else []
    ue_pairs = []
    ue_rows = []
    ec_count = 0
    for semester in semesters:
        semester_ues = list(semester.ues.all().order_by("code", "id"))
        ue_pairs.extend((semester, ue) for ue in semester_ues)
        ec_count += sum(len(ue.ecs.all()) for ue in semester_ues)
    drawer_ues_page = _paginate_items(ue_pairs, ue_page, per_page=8) if ue_pairs else None
    row_map = {}
    for semester, ue in (drawer_ues_page.object_list if drawer_ues_page else []):
        ec_list = list(ue.ecs.all().order_by("title", "id"))
        active_ec_page = str(ec_ue_id or "") == str(ue.id)
        ecs_page = _paginate_items(ec_list, ec_page if active_ec_page else 1, per_page=10) if ec_list else None
        row_map.setdefault(semester.id, {"semester": semester, "ues": []})["ues"].append(
            {
                "ue": ue,
                "ecs_page": ecs_page,
                "ec_count": len(ec_list),
                "active_ec_page": active_ec_page,
            }
        )
    ue_rows = list(row_map.values())

    context.update(
        {
            "drawer_kind": "class",
            "drawer_class": selected_class,
            "drawer_semesters": semesters,
            "drawer_ue_rows": ue_rows,
            "drawer_ues_page": drawer_ues_page,
            "drawer_ec_page": ec_page,
            "drawer_ec_ue_id": ec_ue_id,
            "drawer_selected_semester": selected_semester,
            "drawer_selected_ue": selected_ue,
            "drawer_selected_ec": selected_ec,
            "drawer_ec_count": ec_count,
            "drawer_url": (
                f"{reverse('accounts_portal:it_structure_drawer')}?class_id={selected_class.id}&section={section}"
                + (f"&semester_id={selected_semester.id}" if selected_semester else "")
                + (f"&ue_id={selected_ue.id}" if selected_ue else "")
                + (f"&ec_id={selected_ec.id}" if selected_ec else "")
            ) if selected_class else reverse("accounts_portal:it_structure_drawer"),
        }
    )
    return context


@login_required
def it_import_workspace(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    branch = get_user_branch(request.user)
    classes, selected_class, selected_semester = _resolve_import_selection(request)
    return _render_it_section(
        request,
        "import",
        "portal/informaticien/workflows/import_workspace.html",
        build_import_context(
            branch=branch,
            classes=classes,
            selected_class=selected_class,
            selected_semester=selected_semester,
            session_type=request.GET.get("session_type", "normal"),
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
            session_type=request.POST.get("session_type", "normal"),
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
            session_type=request.POST.get("session_type", "normal"),
            feedback=feedback,
        ),
    )


@login_required
def it_export_notes_excel(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    selection = _resolve_workflow_selection(request)
    academic_class = selection["selected_class"]
    selected_semester = selection["selected_semester"]
    if academic_class is None:
        return HttpResponseForbidden("Classe obligatoire.")
    if selected_semester is None:
        return HttpResponseForbidden("Semestre obligatoire.")
    if not semester_has_active_ecs(selected_semester):
        return HttpResponse(
            "Cette maquette doit etre completee par le Directeur des etudes avant l'export des notes.",
            status=409,
        )

    session_type = (request.GET.get("session") or "normal").strip().lower()
    if session_type not in {"normal", "retake"}:
        return HttpResponse("Session de notes invalide.", status=400)
    score_field = "retake_score" if session_type == "retake" else "normal_score"
    scores_by_cell = {
        (grade.enrollment_id, grade.ec_id): getattr(grade, score_field)
        for grade in ECGrade.objects.filter(
            enrollment__academic_class=academic_class,
            enrollment__academic_year=academic_class.academic_year,
            enrollment__is_active=True,
            ec__ue__semester=selected_semester,
        )
        if getattr(grade, score_field) is not None
    }
    buffer = generate_notes_workbook(
        academic_class=academic_class,
        semester=selected_semester,
        session_type=session_type,
        scores_by_cell=scores_by_cell,
    )
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="notes-{session_type}-{academic_class.id}-'
        f'S{selected_semester.number}.xlsx"'
    )
    log_support_action(
        actor=request.user,
        branch=get_user_branch(request.user),
        action_type=SupportAuditLog.ACTION_EXCEL_EXPORTED,
        target_label=f"Export notes {academic_class.display_name}",
        details=f"Export Excel S{selected_semester.number} - session {session_type}.",
    )
    return response


@login_required
def it_structure_workspace(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    selected_class_id = (request.GET.get("class_id") or request.GET.get("classe") or "").strip()
    student_query = (request.GET.get("student_q") or "").strip()
    section = (request.GET.get("section") or "classes").strip()
    context = build_academic_structure_context(
        branch=get_user_branch(request.user),
        selected_class_id=selected_class_id,
        student_query=student_query,
        section=section,
        class_page=request.GET.get("class_page") or 1,
        student_page=request.GET.get("student_page") or 1,
    )
    context["structure_subnavigation"] = _it_subnavigation(
        url_name="accounts_portal:it_structure_workspace",
        active=section,
        query={"class_id": selected_class_id} if selected_class_id else None,
        definitions=(
            ("classes", "Classes", "graduation-cap", {"section": "classes"}),
            ("maquettes", "Maquettes", "blocks", {"section": "maquettes"}),
            ("affectations", "Affectations", "users-round", {"section": "affectations"}),
        ),
    )
    return _render_it_section(
        request,
        "structure",
        "portal/informaticien/workflows/structure_workspace.html",
        context,
    )


@login_required
def it_structure_drawer(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")

    branch = get_user_branch(request.user)
    context = _build_structure_drawer_context(
        branch=branch,
        class_id=(request.GET.get("class_id") or request.GET.get("id") or request.GET.get("class") or "").strip(),
        semester_id=(request.GET.get("semester_id") or "").strip(),
        ue_id=(request.GET.get("ue_id") or "").strip(),
        ec_id=(request.GET.get("ec_id") or "").strip(),
        section=(request.GET.get("section") or "maquettes").strip(),
        ue_page=request.GET.get("ue_page") or 1,
        ec_page=request.GET.get("ec_page") or 1,
        ec_ue_id=(request.GET.get("ec_ue_id") or "").strip(),
    )
    return render(request, "portal/informaticien/drawers/structure_drawer.html", context)


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
    response["HX-Retarget"] = "#it-dashboard-modal-content"
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
                actor=request.user,
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
                actor=request.user,
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
            delete_ec(branch=branch, actor=request.user, ec_id=request.POST.get("ec_id"))
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
    context["structure_subnavigation"] = _it_subnavigation(
        url_name="accounts_portal:it_structure_workspace",
        active=section,
        query={"class_id": selected_class_id} if selected_class_id else None,
        definitions=(
            ("classes", "Classes", "graduation-cap", {"section": "classes"}),
            ("maquettes", "Maquettes", "blocks", {"section": "maquettes"}),
            ("affectations", "Affectations", "users-round", {"section": "affectations"}),
        ),
    )
    context["toast"] = toast
    response = render(request, "portal/informaticien/workflows/structure_workspace.html", context)
    response["HX-Trigger"] = '{"it-modal-close": true, "it-structure-updated": true}'
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
    return _render_it_section(
        request,
        "archives",
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
    return _render_it_section(
        request,
        "supervision",
        "portal/informaticien/workflows/supervision_workspace.html",
        build_supervision_context(branch=get_user_branch(request.user), page=request.GET.get("page")),
    )


@login_required
def it_catalog_workspace(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    return _render_it_section(request, "catalog", "portal/informaticien/workflows/catalog_workspace.html", build_catalog_context())


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


def _build_accounts_flow_context(request, *, toast=None, temporary_password=None):
    branch = get_user_branch(request.user)
    query = (request.GET.get("q") or "").strip()
    staff_qs = get_scoped_staff_queryset(branch=branch).filter(profile__branch=branch) if branch else get_scoped_staff_queryset(branch=branch).none()
    student_qs = get_scoped_student_queryset(branch=branch) if branch else get_scoped_student_queryset(branch=branch).none()
    if query:
        staff_qs = staff_qs.filter(
            Q(username__icontains=query)
            | Q(email__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )
        student_qs = student_qs.filter(
            Q(matricule__icontains=query)
            | Q(user__username__icontains=query)
            | Q(user__email__icontains=query)
            | Q(inscription__candidature__first_name__icontains=query)
            | Q(inscription__candidature__last_name__icontains=query)
        )
    rows = []
    seen_user_ids = set()
    for user in staff_qs.select_related("profile")[:80]:
        if user.pk == request.user.pk:
            continue
        seen_user_ids.add(user.pk)
        state = get_account_support_state(user)
        if state.is_suspended:
            account_state = "suspendu"
        elif state.is_blocked:
            account_state = "bloque"
        elif user.is_active:
            account_state = "actif"
        else:
            account_state = "inactif"
        rows.append({"user": user, "support_state": state, "account_state": account_state, "kind": "Personnel"})
    for student in student_qs[:80]:
        user = student.user
        if user.pk in seen_user_ids or user.pk == request.user.pk:
            continue
        state = get_account_support_state(user)
        if state.is_suspended:
            account_state = "suspendu"
        elif state.is_blocked:
            account_state = "bloque"
        elif user.is_active:
            account_state = "actif"
        else:
            account_state = "inactif"
        rows.append({
            "user": user,
            "student": student,
            "support_state": state,
            "account_state": account_state,
            "kind": "Étudiant",
        })
    rows.sort(key=lambda row: ((row["user"].get_full_name() or row["user"].username).lower(), row["user"].id))
    rows_page = _paginate_items(rows, request.GET.get("page"), per_page=20)

    return {
        "branch": branch,
        "query": query,
        "rows": rows_page.object_list,
        "rows_page": rows_page,
        "toast": toast,
        "temporary_password": temporary_password,
    }


@login_required
def it_accounts_flow_workspace(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    return _render_it_section(
        request,
        "accounts",
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
    target_user = _get_scoped_it_target_user(branch=branch, user_id=request.POST.get("target_user_id"))
    if target_user is None or target_user == request.user:
        return HttpResponseForbidden("Action hors annexe refusee.")
    action = (request.POST.get("action") or "").strip()
    toast = None
    temporary_password = None

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
    elif action == "unblock":
        unblock_account(actor=request.user, branch=branch, target_user=target_user)
        toast = {"level": "success", "message": "Compte debloque."}
    elif action == "reactivate":
        reactivate_account(actor=request.user, branch=branch, target_user=target_user)
        toast = {"level": "success", "message": "Compte reactive."}
    elif action == "reset_password":
        temp_password = create_temp_password()
        target_user.set_password(temp_password)
        target_user.save(update_fields=["password"])
        from accounts.session_security import mark_temporary_password
        mark_temporary_password(target_user, updated_by=request.user)
        log_support_action(
            actor=request.user,
            branch=branch,
            action_type="password_reset",
            target_user=target_user,
            target_label=target_user.get_full_name() or target_user.username,
            details="Reset mot de passe depuis workflow comptes informaticien.",
        )
        # La valeur en clair n'est jamais mise dans SupportAuditLog. Elle est
        # transmise une seule fois au fragment modal persistant.
        temporary_password = temp_password
    else:
        toast = {"level": "error", "message": "Action compte inconnue."}

    if temporary_password and request.headers.get("HX-Request") == "true":
        response = render(
            request,
            "portal/informaticien/workflows/temporary_password_modal.html",
            {"temporary_password": temporary_password},
        )
        response["HX-Trigger-After-Settle"] = '{"it-temporary-password-ready": true}'
        return response

    response = render(
        request,
        "portal/informaticien/workflows/accounts_workspace.html",
        _build_accounts_flow_context(request, toast=toast, temporary_password=temporary_password),
    )
    if temporary_password:
        # HTMX déclenche cet évènement après le rendu et les swaps OOB : le
        # modal certifié reçoit donc déjà le mot de passe temporaire.
        response["HX-Trigger-After-Settle"] = '{"it-temporary-password-ready": true}'
    return response


@login_required
def it_user_modal(request, user_id):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")

    branch = get_user_branch(request.user)
    target_user = _get_scoped_it_target_user(branch=branch, user_id=user_id)
    if target_user is None:
        return HttpResponseForbidden("Action hors annexe refusee.")
    return render(request, "portal/informaticien/workflows/user_modal.html", _build_it_user_modal_context(target_user=target_user))


@login_required
def it_user_modal_save(request, user_id):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    if request.method != "POST":
        return HttpResponseForbidden("Methode non autorisee.")

    branch = get_user_branch(request.user)
    target_user = _get_scoped_it_target_user(branch=branch, user_id=user_id)
    if target_user is None or target_user == request.user:
        return HttpResponseForbidden("Action hors annexe refusee.")

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

    context = _build_it_user_modal_context(target_user=target_user)
    context["toast"] = {"level": "success", "message": "Utilisateur mis a jour."}
    return render(request, "portal/informaticien/workflows/user_modal.html", context)


@login_required
def it_user_sessions(request, user_id):
    """Historique de connexions paginé, strictement limité à l'utilisateur scopé."""
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    branch = get_user_branch(request.user)
    target_user = _get_scoped_it_target_user(branch=branch, user_id=user_id)
    if target_user is None:
        return HttpResponseForbidden("Action hors annexe refusee.")
    sessions_page = _paginate_items(
        AccountSessionRecord.objects.filter(user=target_user).order_by("-started_at"),
        request.GET.get("page"),
        per_page=10,
    )
    return render(request, "portal/informaticien/workflows/user_sessions.html", {
        "target_user": target_user,
        "sessions_page": sessions_page,
    })


@login_required
def it_branch_settings_workspace(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    branch = get_user_branch(request.user)
    settings = get_branch_settings(branch=branch)
    return _render_it_section(
        request,
        "settings",
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

    context = _build_retake_modal_context(request)
    academic_class = context["academic_class"]
    semester = context["semester"]
    state = context["state"]
    if academic_class is None or semester is None:
        return HttpResponse("Selection classe/semestre invalide.", status=400)
    if state is None or not state.retake_ready:
        return HttpResponse(
            "Le rattrapage n'est disponible qu'apres cloture de la session normale, pour les etudiants concernes.",
            status=409,
        )
    return render(request, "portal/informaticien/workflows/retake_modal.html", context)


@login_required
def it_my_account_workspace(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    profile = getattr(request.user, "profile", None)
    return _render_it_section(
        request,
        "settings",
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

    try:
        pdf_bytes = _render_student_card_pdf(request, student, branch)
    except ValidationError as exc:
        return HttpResponse(str(exc), status=409)
    buffer = BytesIO(pdf_bytes)
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
        content_type="application/pdf",
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

    students = get_it_students_for_class(academic_class=academic_class).filter(
        user__academic_enrollments__is_active=True,
    )
    try:
        pdf_bytes = _render_class_cards_pdf(request, list(students), academic_class, branch)
    except ValidationError as exc:
        return HttpResponse(str(exc), status=409)
    buffer = BytesIO(pdf_bytes)
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
        content_type="application/pdf",
    )


@login_required
def it_branch_student_cards_pdf(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    branch = get_user_branch(request.user)
    students = list(
        get_scoped_student_queryset(branch=branch).filter(
            is_active=True,
            inscription__is_archived=False,
            user__academic_enrollments__is_active=True,
            user__academic_enrollments__is_archived=False,
        ).distinct()
    )
    try:
        pdf_bytes = _render_class_cards_pdf(request, students, None, branch)
    except ValidationError as exc:
        return HttpResponse(str(exc), status=409)
    log_support_action(
        actor=request.user,
        branch=branch,
        action_type=SupportAuditLog.ACTION_STUDENT_CARD_GENERATED,
        target_label=f"Cartes etudiants {branch.code or branch.id}",
        details=f"{len(students)} carte(s) etudiante(s) active(s) generee(s).",
    )
    return FileResponse(
        BytesIO(pdf_bytes),
        as_attachment=request.GET.get("preview") != "1",
        filename=f"cartes-etudiants-{branch.code or branch.id}.pdf",
        content_type="application/pdf",
    )


@login_required
def it_staff_card_pdf(request, staff_id):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    branch = get_user_branch(request.user)
    staff_user = get_object_or_404(
        get_scoped_staff_queryset(branch=branch).filter(profile__employment_status="active"),
        pk=staff_id,
    )
    try:
        pdf_bytes = _render_staff_card_pdf(request, staff_user.profile, branch)
    except ValidationError as exc:
        return HttpResponse(str(exc), status=409)
    log_support_action(
        actor=request.user,
        branch=branch,
        action_type=SupportAuditLog.ACTION_STUDENT_CARD_GENERATED,
        target_user=staff_user,
        target_label=f"Carte personnel {staff_user.profile.employee_code or staff_user.id}",
        details="Carte professionnelle individuelle generee depuis le dashboard informaticien.",
    )
    return FileResponse(
        BytesIO(pdf_bytes),
        as_attachment=request.GET.get("preview") != "1",
        filename=f"carte-personnel-{staff_user.profile.employee_code or staff_user.id}.pdf",
        content_type="application/pdf",
    )


@login_required
def it_branch_staff_cards_pdf(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")
    branch = get_user_branch(request.user)
    staff = list(
        get_scoped_staff_queryset(branch=branch)
        .filter(profile__employment_status="active")
        .select_related("profile")
    )
    try:
        pdf_bytes = _render_staff_cards_pdf(request, [user.profile for user in staff], branch)
    except ValidationError as exc:
        return HttpResponse(str(exc), status=409)
    log_support_action(
        actor=request.user,
        branch=branch,
        action_type=SupportAuditLog.ACTION_STUDENT_CARD_GENERATED,
        target_label=f"Cartes personnel {branch.code or branch.id}",
        details=f"{len(staff)} carte(s) professionnelle(s) generee(s).",
    )
    return FileResponse(
        BytesIO(pdf_bytes),
        as_attachment=request.GET.get("preview") != "1",
        filename=f"cartes-personnel-{branch.code or branch.id}.pdf",
        content_type="application/pdf",
    )


def _get_or_create_carte(student, branch):
    from datetime import date
    from students.models import CarteEtudiant

    enrollment = (
        student.user.academic_enrollments.select_related("academic_class__academic_year")
        .filter(is_active=True)
        .order_by("-created_at")
        .first()
    )
    academic_year = None
    if enrollment and enrollment.academic_class:
        academic_year = getattr(enrollment.academic_class, "academic_year", None)
    if academic_year is None and enrollment:
        academic_year = getattr(enrollment, "academic_year", None)

    today = date.today()
    annee = str(academic_year)[:9] if academic_year else f"{today.year}-{today.year + 1}"
    code_annexe = (getattr(branch, "code", None) or (branch.name[:20] if branch else "ESFE"))
    date_expiration = date(today.year + 1, 9, 30)

    carte, _ = CarteEtudiant.objects.get_or_create(
        etudiant=student,
        annee=annee,
        defaults={
            "code_annexe": code_annexe,
            "date_expiration": date_expiration,
            "statut": "active",
        },
    )
    if not carte.is_valide:
        raise ValidationError("Cette carte est perdue, revoquee ou expiree. Reemettez-la apres traitement administratif.")
    return carte


def _card_academic_year():
    academic_year = AcademicYear.objects.filter(is_active=True).order_by("-start_date").first()
    if academic_year:
        return academic_year.name
    today = timezone.localdate()
    return f"{today.year}-{today.year + 1}"


def _card_expiration_date():
    from datetime import date

    today = timezone.localdate()
    return date(today.year + 1, 9, 30)


def _get_or_create_staff_card(profile, branch):
    annee = _card_academic_year()
    code_annexe = getattr(branch, "code", "") or (branch.name[:20] if branch else "ESFE")
    carte, _ = CartePersonnel.objects.get_or_create(
        profile=profile,
        annee=annee,
        defaults={
            "code_annexe": code_annexe,
            "date_expiration": _card_expiration_date(),
            "statut": "active",
        },
    )
    if not carte.is_valide:
        raise ValidationError("Cette carte professionnelle est perdue, revoquee ou expiree.")
    return carte


def _public_card_url(*, token, staff=False):
    route = "students:portail_verify_staff_token" if staff else "students:portail_verify_token"
    return f"{settings.BASE_URL}{reverse(route, args=[token])}"


def _render_card_print_sheets(request, *, cards, card_type):
    from django.template.loader import render_to_string
    from weasyprint import HTML

    pages = [cards[index:index + 8] for index in range(0, len(cards), 8)]
    html_str = render_to_string(
        "students/cards_print_sheet.html",
        {"card_pages": pages, "card_type": card_type},
        request=request,
    )
    return HTML(string=html_str, base_url=settings.BASE_URL).write_pdf()


def _render_student_card_pdf(request, student, branch=None):
    from weasyprint import HTML
    from django.template.loader import render_to_string
    from students.services.card_security import signer_carte_reference, generer_code_lisible, generer_qr_png, generer_qr_svg
    from students.views_carte import _logo_data_uri, _get_classe

    if branch is None:
        branch = get_user_branch(request.user)

    carte = _get_or_create_carte(student, branch)
    token = signer_carte_reference(
        reference=str(carte.public_reference), annee=carte.annee,
        annexe=carte.code_annexe, kind="student",
    )
    verify_url = _public_card_url(token=token)

    ctx = {
        "carte": carte,
        "etudiant": student,
        "classe": _get_classe(carte),
        "qr_png": generer_qr_png(verify_url),
        "qr_svg": generer_qr_svg(verify_url),
        "code_verification": generer_code_lisible(token),
        "logo_data_uri": _logo_data_uri(),
    }
    ctx["branch_name"] = getattr(branch, "name", "") or carte.code_annexe
    return _render_card_print_sheets(request, cards=[ctx], card_type="student")


def _render_class_cards_pdf(request, students_list, academic_class, branch=None):
    from students.services.card_security import signer_carte_reference, generer_code_lisible, generer_qr_png, generer_qr_svg
    from students.views_carte import _get_classe, _logo_data_uri

    if branch is None:
        branch = get_user_branch(request.user)

    logo = _logo_data_uri()
    cards = []

    for student in students_list:
        carte = _get_or_create_carte(student, branch)
        token = signer_carte_reference(
            reference=str(carte.public_reference), annee=carte.annee,
            annexe=carte.code_annexe, kind="student",
        )
        verify_url = _public_card_url(token=token)
        cards.append({
            "carte": carte,
            "etudiant": student,
            "classe": str(academic_class) if academic_class else _get_classe(carte),
            "qr_png": generer_qr_png(verify_url),
            "qr_svg": generer_qr_svg(verify_url),
            "code_verification": generer_code_lisible(token),
            "logo_data_uri": logo,
            "branch_name": getattr(branch, "name", "") or carte.code_annexe,
        })

    return _render_card_print_sheets(request, cards=cards, card_type="student")


def _render_staff_card_pdf(request, profile, branch=None):
    from students.services.card_security import generer_code_lisible, generer_qr_png, generer_qr_svg, signer_carte_reference
    from students.views_carte import _logo_data_uri

    carte = _get_or_create_staff_card(profile, branch)
    token = signer_carte_reference(
        reference=str(carte.public_reference), annee=carte.annee,
        annexe=carte.code_annexe, kind="staff",
    )
    context = {
        "carte": carte,
        "profile": profile,
        "qr_png": generer_qr_png(_public_card_url(token=token, staff=True)),
        "qr_svg": generer_qr_svg(_public_card_url(token=token, staff=True)),
        "code_verification": generer_code_lisible(token),
        "logo_data_uri": _logo_data_uri(),
        "branch_name": getattr(branch, "name", "") or carte.code_annexe,
    }
    return _render_card_print_sheets(request, cards=[context], card_type="staff")


def _get_scoped_it_target_user(*, branch, user_id):
    if not str(user_id).isdigit():
        return None
    target_user = get_user_model().objects.select_related("profile").filter(pk=int(user_id)).first()
    if target_user is None or not can_manage_user_in_branch(branch=branch, target_user=target_user):
        return None
    return target_user


def _build_it_user_modal_context(*, target_user):
    student = Student.objects.select_related(
        "inscription__candidature__branch",
        "inscription__candidature__programme",
    ).filter(user=target_user).first()
    enrollment = (
        target_user.academic_enrollments.select_related("academic_class", "programme", "branch")
        .filter(is_active=True).first()
        if student else None
    )
    return {
        "target_user": target_user,
        "profile": getattr(target_user, "profile", None),
        "student": student,
        "enrollment": enrollment,
        "support_state": get_account_support_state(target_user),
        "security_events": list(AccountSecurityEvent.objects.filter(user=target_user).order_by("-created_at")[:12]),
        "sessions": list(AccountSessionRecord.objects.filter(user=target_user).order_by("-started_at")[:5]),
    }


def _render_staff_cards_pdf(request, profiles, branch=None):
    from students.services.card_security import generer_code_lisible, generer_qr_png, generer_qr_svg, signer_carte_reference
    from students.views_carte import _logo_data_uri

    cards = []
    for profile in profiles:
        carte = _get_or_create_staff_card(profile, branch)
        token = signer_carte_reference(
            reference=str(carte.public_reference), annee=carte.annee,
            annexe=carte.code_annexe, kind="staff",
        )
        verify_url = _public_card_url(token=token, staff=True)
        cards.append({
            "carte": carte, "profile": profile,
            "qr_png": generer_qr_png(verify_url), "qr_svg": generer_qr_svg(verify_url),
            "code_verification": generer_code_lisible(token), "logo_data_uri": _logo_data_uri(),
            "branch_name": getattr(branch, "name", "") or carte.code_annexe,
        })
    return _render_card_print_sheets(request, cards=cards, card_type="staff")


@login_required
def it_notifications_workspace(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")

    user = request.user

    # Return just the unread count badge (used by the bell icon)
    if request.GET.get("count_only"):
        unread = NotificationMessage.objects.filter(
            recipient=user, read_at__isnull=True,
        ).count()
        badge = (
            f'<span id="it-notif-badge" class="absolute -right-1 -top-1 grid min-h-[18px] min-w-[18px] '
            f'place-items-center rounded-full bg-red-500 px-1 text-[10px] font-black leading-none text-white">'
            f'{unread}</span>'
        )
        return HttpResponse(badge)

    # Dropdown partial for the bell icon (7 latest notifications)
    if request.GET.get("partial") == "dropdown":
        from notification_center.selectors import get_user_notifications, get_user_unread_count
        notifs = get_user_notifications(user, limit=7)
        unread = get_user_unread_count(user)
        return render(request, "portal/informaticien/partials/notifications_dropdown_it.html", {
            "notifications": notifs,
            "unread_count": unread,
        })

    q = request.GET.get("q", "")
    channel = request.GET.get("channel", "all")
    status_filter = request.GET.get("status", "")
    priority = request.GET.get("priority", "")
    source = request.GET.get("source", "")
    page = request.GET.get("page", 1)
    notification_id = request.GET.get("notification_id")

    qs = NotificationMessage.objects.filter(
        Q(recipient=user) | Q(legacy_source__icontains="system"),
    )

    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(body__icontains=q))
    if channel and channel != "all":
        qs = qs.filter(channel=channel)
    if status_filter == "unread":
        qs = qs.filter(read_at__isnull=True)
    elif status_filter == "read":
        qs = qs.filter(read_at__isnull=False)
    elif status_filter == "failed":
        qs = qs.filter(status=NotificationMessage.STATUS_FAILED)
    if priority:
        qs = qs.filter(priority=priority)
    if source:
        qs = qs.filter(Q(event__source_app__icontains=source) | Q(legacy_source__icontains=source))

    qs = qs.select_related("event", "recipient").prefetch_related("deliveries").order_by("-created_at")

    paginator = Paginator(qs, 12)
    try:
        page_obj = paginator.page(page)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.page(1)

    notifications = list(page_obj)
    selected_notification = None
    if notification_id:
        try:
            selected_notification = NotificationMessage.objects.filter(
                id=notification_id,
            ).select_related("event").prefetch_related("deliveries").first()
        except ValueError:
            pass

    all_user_notifs = NotificationMessage.objects.filter(recipient=user)
    stats = {
        "total": all_user_notifs.count(),
        "unread": all_user_notifs.filter(read_at__isnull=True).count(),
        "critical": all_user_notifs.filter(priority=NotificationMessage.PRIORITY_CRITICAL).count(),
        "email": all_user_notifs.filter(channel=NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL).count(),
        "failed": all_user_notifs.filter(status=NotificationMessage.STATUS_FAILED).count(),
        "by_source": list(
            all_user_notifs.values("event__source_app").annotate(total=Count("id")).order_by("-total")[:5]
        ),
    }
    unread_count = stats["unread"]

    filters = {
        "q": q,
        "channel": channel,
        "status": status_filter,
        "priority": priority,
        "source": source,
    }

    return _render_it_section(request, "notifications", "portal/informaticien/workflows/notifications_workspace.html", {
        "notifications": notifications,
        "page_obj": page_obj,
        "stats": stats,
        "unread_count": unread_count,
        "channels": NotificationMessage.CHANNEL_CHOICES,
        "priorities": NotificationMessage.PRIORITY_CHOICES,
        "sources": list(
            NotificationMessage.objects.filter(recipient=user)
            .values_list("event__source_app", flat=True)
            .distinct()[:10]
        ),
        "filters": filters,
        "selected_notification": selected_notification,
        "toast": None,
    })


@login_required
def it_notifications_action(request):
    if not _require_it_support(request):
        return HttpResponseForbidden("Acces refuse.")

    if request.method != "POST":
        return HttpResponse("Methode non autorisee.", status=405)

    user = request.user
    action = request.POST.get("action", "")
    notification_id = request.POST.get("notification_id")

    toast = None

    if action == "mark_read" and notification_id:
        updated = NotificationMessage.objects.filter(
            id=notification_id, recipient=user, read_at__isnull=True,
        ).update(read_at=timezone.now(), status=NotificationMessage.STATUS_READ)
        if updated:
            toast = {"level": "success", "message": "Notification marquee comme lue."}
        else:
            toast = {"level": "error", "message": "Notification deja lue ou introuvable."}

    elif action == "mark_unread" and notification_id:
        NotificationMessage.objects.filter(
            id=notification_id, recipient=user,
        ).update(read_at=None, status=NotificationMessage.STATUS_DELIVERED)
        toast = {"level": "success", "message": "Notification marquee comme non lue."}

    elif action == "mark_all_read":
        count = NotificationMessage.objects.filter(
            recipient=user, read_at__isnull=True,
        ).update(read_at=timezone.now(), status=NotificationMessage.STATUS_READ)
        toast = {"level": "success", "message": f"{count} notification(s) marquee(s) comme lue(s)."}

    else:
        toast = {"level": "error", "message": f"Action inconnue: {action}"}

    # Re-render workspace with updated state
    from django.http import QueryDict
    get_params = QueryDict(mutable=True)
    for key in ("channel", "status", "priority", "source", "q", "page"):
        val = request.POST.get(key, "")
        if val:
            get_params[key] = val

    from django.test.client import RequestFactory
    factory = RequestFactory()
    fake_get = factory.get(f"/?{get_params.urlencode()}")
    fake_get.user = user
    fake_get.GET = get_params
    fake_get.META = request.META

    response = it_notifications_workspace(fake_get)
    if hasattr(response, "context_data"):
        response.context_data["toast"] = toast
    elif hasattr(response, "context"):
        response.context["toast"] = toast
    return response
