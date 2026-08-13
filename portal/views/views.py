import json
from collections import defaultdict
import csv
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.core.validators import validate_email
from django.db.models import Count, Max, Q, Sum
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_GET, require_POST

from academics.models import (
    AcademicBulletin,
    AcademicCalendar,
    AcademicCalendarEntry,
    AcademicClass,
    AcademicDiplomaAward,
    AcademicEnrollment,
    AcademicScheduleEvent,
    AcademicYear,
    EC,
    ECChapter,
    ECContent,
    ECGrade,
    LessonLog,
    Semester,
    UE,
    WeeklyScheduleSlot,
)
from academics.permissions import (
    BULLETIN_MANAGEMENT_POSITIONS,
    DIRECTOR_DASHBOARD_POSITIONS,
    can_manage_bulletins,
    can_manage_diplomas,
    is_global_academic_user,
    require_director_branch_scope,
)
from academic_cycle.services.academic_excel_reports import build_academic_report_xlsx, xlsx_response
from academics.services.documents import (
    generate_annual_bulletins_for_class,
    generate_semester_bulletins_for_class,
    prepare_diploma_awards_for_class,
)
from admissions.models import Candidature
from academic_cycle.services.audit_service import log_action
from accounts.forms import SystemProfileForm, UserPreferenceForm
from accounts.models import BranchExpense, Profile, SensitiveActionRequest, UserPreference
from accounts.services.sensitive_actions import SensitiveActionError, confirm_sensitive_action, request_sensitive_action
from academics.services.lesson_log_service import create_lesson_log, update_lesson_log
from academics.services.schedule_service import (
    cancel_schedule_event,
    create_schedule_event,
    create_weekly_schedule_slot,
    deactivate_weekly_schedule_slot,
    get_class_week_schedule,
    get_teacher_week_schedule,
    get_director_schedule_overview,
    list_weekly_slots_for_class,
    serialize_weekly_slot_for_ui,
    update_weekly_schedule_slot,
)
from academics.services.semester import compute_semester_result
from academics.services.grading import resolve_threshold
from academics.services.workflow import can_publish_semester
from academics.services.teacher_assignment_service import (
    activate_teacher_assignment,
    archive_teacher_assignment,
    create_teacher_assignment,
    suspend_teacher_assignment,
    update_teacher_assignment,
)
from accounts.access import can_access, get_user_position, get_user_scope
from accounts.dashboards.helpers import get_user_branch, paginate_queryset
from branches.models import Branch
from inscriptions.models import Inscription
from payments.models import Payment
from notification_center.presentation import get_safe_action_url
from notification_center.selectors import (
    get_notification_center_queryset,
    get_notification_center_stats,
    get_notification_filter_options,
    get_user_in_app_messages,
    get_user_unread_count,
)
from academics.services.calendar_service import (
    create_calendar,
    create_calendar_entry,
    update_calendar_entry,
)
from portal.permissions import get_post_login_portal_url
from portal.services import (
    build_certified_dashboard_shell,
    build_role_dashboard_shell,
    build_it_dashboard_context,
    build_teacher_class_detail_context,
    build_teacher_dashboard_context,
    build_teacher_overview_context,
    build_teacher_classes_context,
    build_teacher_logs_context,
    build_teacher_notifications_context,
    build_teacher_salary_context,
    build_teacher_schedule_context,
    build_teacher_supports_context,
    build_teacher_lesson_log_context,
)
from portal.services.teacher_dashboard_service import (
    TEACHER_EXCLUDED_NOTIFICATION_SOURCES,
    _validate_content_file_extension,
    build_teacher_support_workspace_context,
    build_teacher_settings_context,
    declare_teacher_absence_for_event,
    delete_teacher_content,
    get_teacher_content_for_edit,
    update_teacher_content,
    update_teacher_dashboard_preference,
)
from students.models import TeacherAttendance
from notifier.models import MessageAttachment, NotificationMessage
from notifier.services import NotificationBus
from portal.services.director import (
    add_transfer_document,
    build_director_administrative_document_context,
    build_director_calendar_context,
    build_director_classroom_ops_context,
    build_director_document_context,
    build_director_exam_sessions_context,
    build_director_salary_context,
    build_director_planning_assignment_context,
    build_director_programme_context,
    build_director_tasks_center,
    build_director_teacher_assignment_context,
    build_director_timetable_context,
    build_director_transfer_context,
    build_weekly_timetable_grid,
    create_transfer_request,
    create_teacher_with_account,
    generate_teacher_contract_pdf,
    get_transfer_request_for_director,
    review_teacher_document,
    review_transfer_document,
    review_transfer_request,
    send_director_internal_message,
    upload_teacher_document,
)
from portal.services.director_dashboard_presentation import (
    build_director_dashboard_presentation,
)
from portal.services.supervisor_service import build_class_detail_context
from portal.services.academic_structure_service import (
    delete_ec,
    save_academic_class,
    save_ec,
    save_semester,
    save_ue,
)
from portal.services.it_support_service import (
    add_support_ticket_comment,
    assign_support_ticket,
    build_diagnostic_payload,
    can_manage_user_in_branch,
    create_support_ticket,
    create_temp_password,
    get_support_ticket_metrics,
    get_support_ticket_queryset,
    reactivate_account,
    get_scoped_staff_queryset,
    log_support_action,
    suspend_account,
    unblock_account,
    update_account_email,
    update_support_ticket_status,
)
from portal.models import AdministrativeDocument, DirectorTeacherAssignment, SupportAuditLog, SupportTicket, TeacherDocument, TransferRequest
from portal.forms import (
    DirectorAdministrativeDocumentForm,
    DirectorECForm,
    DirectorEvaluationForm,
    DirectorExamSessionForm,
    DirectorInternalMessageForm,
    DirectorProgrammeClassForm,
    DirectorSemesterForm,
    DirectorTeacherAssignmentForm,
    DirectorTeacherCreateForm,
    DirectorTeacherDocumentForm,
    DirectorTransferForm,
    DirectorTransferDocumentForm,
    DirectorUEForm,
    DirectorWeeklyScheduleSlotForm,
)
from portal.services.director.calendar_mgt_service import validate_entry_business_rules
from portal.views.it_grades_import import build_it_grade_selection_context
from portal.dg.services import (
    build_dg_dashboard_context,
    build_dg_drawer_context,
    build_dg_section_context,
)
from portal.dg.forms import DgCouponForm, DgRecruitmentForm
from portal.dg.rh_service import create_staff_from_recruitment
from portal.dg.coupons_service import create_coupon, get_coupon_detail, list_coupons, toggle_coupon
from portal.dg.actions_service import (
    create_finance_followup,
    escalate_student_case,
    resolve_attendance_alert,
    resolve_student_case,
)
from portal.dg.executive_actions import (
    arbitrate_decision,
    deliver_diploma,
    nominate_branch_manager,
    publish_class_diplomas,
    transition_branch_cycle,
    validate_closure,
)
from students.models import AttendanceAlert, Student, StudentAttendance, StudentCase, StudentYearDecision
from secretary.permissions import is_secretary


def _build_portal_context(request, *, page_title, module_cards):
    scope = get_user_scope(request.user)
    user_display_name = request.user.get_full_name() or request.user.username
    try:
        secretary_url = reverse("accounts_portal:portal_secretary")
    except NoReverseMatch:
        secretary_url = ""

    return {
        "page_title": page_title,
        "user_display_name": user_display_name,
        "detected_role": scope.get("role") or "public",
        "scope": scope,
        "module_cards": module_cards,
        "secretary_available": is_secretary(request.user),
        "secretary_url": secretary_url,
        "welcome_message": f"Bienvenue {user_display_name}, vous etes connecte en tant que {scope.get('role') or 'public'}",
    }


def _resolve_academic_branch(request):
    return get_user_branch(request.user)


def _resolve_director_branch(request, *, additional_scoped_positions=None):
    return require_director_branch_scope(
        request.user,
        additional_scoped_positions=additional_scoped_positions,
    )


def _build_academic_dashboard_context(request, *, page_title, page_kicker, sidebar_links, highlight):
    branch = _resolve_academic_branch(request)
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=7)
    overview = get_director_schedule_overview(branch, week_start) if branch else {"stats": {}, "quality": {"score": 0, "warnings": []}, "alerts": [], "timetable": []}

    classes_qs = AcademicClass.objects.select_related("programme", "academic_year", "branch").filter(is_active=True)
    if branch:
        classes_qs = classes_qs.filter(branch=branch)
    classes_qs = classes_qs.annotate(student_count=Count("enrollments")).order_by("level", "programme__title")

    classes = list(classes_qs[:8])
    current_week_events_qs = AcademicScheduleEvent.objects.select_related("academic_class", "teacher", "ec", "branch").filter(
        start_datetime__date__gte=week_start,
        start_datetime__date__lt=week_end,
    )
    if branch:
        current_week_events_qs = current_week_events_qs.filter(branch=branch)
    current_week_events = list(current_week_events_qs.order_by("start_datetime", "id")[:10])

    total_students = AcademicEnrollment.objects.filter(branch=branch).count() if branch else AcademicEnrollment.objects.count()
    total_classes = classes_qs.count()
    total_teachers = (
        AcademicScheduleEvent.objects.filter(branch=branch).values("teacher_id").distinct().count()
        if branch
        else AcademicScheduleEvent.objects.values("teacher_id").distinct().count()
    )

    schedule_stats = overview.get("stats", {})
    quality = overview.get("quality", {})
    alerts = overview.get("alerts", [])
    timetable = overview.get("timetable", [])
    class_load_items = sorted(
        (schedule_stats.get("class_load") or {}).items(),
        key=lambda item: (-item[1]["hours"], item[0]),
    )[:5]
    teacher_load_items = sorted(
        (schedule_stats.get("teacher_load") or {}).items(),
        key=lambda item: (-item[1]["hours"], item[0]),
    )[:5]

    return {
        **_build_portal_context(
            request,
            page_title=page_title,
            module_cards=highlight,
        ),
        "dashboard_kind": page_kicker,
        "branch": branch,
        "week_start": week_start,
        "week_end": week_end,
        "current_week_events": current_week_events,
        "classes": classes,
        "total_students": total_students,
        "total_classes": total_classes,
        "total_teachers": total_teachers,
        "schedule_stats": schedule_stats,
        "quality": quality,
        "alerts": alerts[:8],
        "timetable": timetable,
        "class_load_items": class_load_items,
        "teacher_load_items": teacher_load_items,
        "sidebar_links": sidebar_links,
    }


def _build_it_dashboard_context(request):
    return build_it_dashboard_context(
        request,
        branch=_resolve_academic_branch(request),
        base_context_builder=_build_portal_context,
    )


def _deny_portal_access(request):
    return HttpResponseForbidden("Acces portail refuse.")


def _redirect_supervisor_dashboard(anchor="overview"):
    base_url = reverse("accounts_portal:portal_dashboard")
    return redirect(f"{base_url}#{anchor}")


def _redirect_it_dashboard(request, anchor="diagnostics"):
    params = []
    query = (request.POST.get("q") or request.GET.get("q") or "").strip()
    kind = (request.POST.get("kind") or request.GET.get("kind") or "").strip()
    object_id = (request.POST.get("id") or request.GET.get("id") or "").strip()
    if query:
        params.append(f"q={query}")
    if kind:
        params.append(f"kind={kind}")
    if object_id:
        params.append(f"id={object_id}")
    url = reverse("accounts_portal:portal_dashboard")
    if params:
        url = f"{url}?{'&'.join(params)}"
    return redirect(f"{url}#{anchor}")


def _store_it_support_feedback(request, *, level, title, message, password=None):
    request.session["it_support_feedback"] = {
        "level": level,
        "title": title,
        "message": message,
        "password": password,
    }


def _parse_optional_time(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError as exc:
        raise ValidationError("Le format d'heure attendu est HH:MM.") from exc


def _position_required(expected_positions):
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            position = get_user_position(request.user)
            if position not in expected_positions:
                return _deny_portal_access(request)
            return view_func(request, *args, **kwargs)
        return login_required(wrapper)
    return decorator


def _build_director_sidebar_items():
    return [
        {"key": "home",              "label": "Accueil",          "icon": "layout-dashboard"},
        {"key": "calendrier",        "label": "Calendrier",        "icon": "calendar-days"},
        {
            "key": "evaluations_calendar",
            "label": "Évaluations",
            "icon": "clipboard-check",
            "children": [
                {"key": "evaluations_calendar", "label": "Sessions examens"},
                {"key": "evaluations",          "label": "Résultats & Notes"},
            ],
        },
        {"key": "enseignants",       "label": "Enseignants",       "icon": "user-check"},
        {"key": "programme",         "label": "Programmes",        "icon": "book-open"},
        {"key": "planification",     "label": "Emploi du temps",   "icon": "calendar-range"},
        {"key": "correspondances",   "label": "Documents",         "icon": "mail"},
    ]


def _build_director_class_rows(class_cards, branch=None):
    rows = []
    for item in class_cards[:6]:
        bucket = item.get("workflow_bucket", "")
        if bucket == "ready":
            status_badge = {"component": "academic_badge", "label": "Prête", "tone": "success"}
        elif bucket == "rejected":
            status_badge = {"component": "academic_badge", "label": "À revoir", "tone": "danger"}
        else:
            status_badge = {"component": "academic_badge", "label": "En cours", "tone": "warning"}
        progress = item.get("progress", 0)
        progress_html = (
            f'<div class="flex items-center gap-2">'
            f'<div class="h-2 flex-1 rounded-full bg-[color:var(--surface-2)] overflow-hidden">'
            f'<div class="h-full rounded-full bg-[color:var(--school-primary)]" style="width:{progress}%"></div>'
            f'</div>'
            f'<span class="text-xs font-bold text-[color:var(--muted)]">{progress}%</span>'
            f'</div>'
        )
        rows.append({
            "id": item["class"].id,
            "cells": [
                {"value": item["class"].display_name, "class": "font-semibold"},
                {"value": str(item.get("student_count") or 0)},
                {"html": progress_html},
                status_badge,
            ],
        })
    return rows


def _render_director_dashboard(request):
    workspace_context = _build_director_workspace_context(request)
    if workspace_context.get("section") == "messagerie":
        workspace_context.update(_director_notifications_context(request))
    branch = workspace_context.get("branch")
    context = {
        **_build_portal_context(
            request,
            page_title="Dashboard Direction des Etudes",
            module_cards=["Pilotage academique", "Resultats", "Enseignants"],
        ),
        "dashboard_kind": "Direction des etudes",
        **workspace_context,
        "quality_score": (workspace_context.get("quality") or {}).get("score", 0),
        "home_alerts_count": len(workspace_context.get("alerts") or []),
        "lesson_logs_count": len(workspace_context.get("recent_lesson_logs") or []),
    }
    context.update(build_director_dashboard_presentation(request, workspace_context))
    context.update(_director_account_profile_context(request))
    if context.get("director_active_section") == "home":
        workspace_template = "portal/staff/director/partials/home.html"
    elif context.get("director_active_section") == "messagerie":
        workspace_template = "portal/staff/director/partials/notifications/workspace.html"
    else:
        workspace_template = "portal/staff/director/partials/workspace.html"
    context.update(
        build_certified_dashboard_shell(
            role=get_user_position(request.user) or "director_of_studies",
            key="director",
            page_title=context["page_title"],
            title="Direction des Études",
            subtitle="Direction des Études",
            context_label=context.get("director_context_label") or "",
            user_name=request.user.get_full_name() or request.user.username,
            navigation=context.get("director_navigation") or [],
            active_section=context.get("director_active_section") or "home",
            workspace_template=workspace_template,
            topbar_template="portal/staff/director/partials/topbar_fragments.html",
            script_path="src/js/portal/director_dashboard.js",
            modal_title="Gestion académique",
        )
    )
    return render(request, "portal/staff/director_dashboard.html", context)


def _parse_director_section(request, default="home"):
    section = (request.GET.get("section") or request.POST.get("section") or default).strip().lower()
    aliases = {
        # anciens noms → nouveaux noms
        "operations": "planification",
        "assignments": "planification",
        "edt": "planification",
        "schedule": "planification",
        "planning": "planification",
        "academic": "programme",
        "classes": "programme",
        "teachers": "enseignants",
        "documents": "enseignants",
        "transfers": "transferts",
        "results": "evaluations",
        "publications": "evaluations",
        "settings": "enseignants",
        "stats": "evaluations",
        "notifications": "messagerie",
        "finance": "salaire",
        "logs": "evaluations",
        "students": "programme",
        "anomalies": "evaluations",
    }
    section = aliases.get(section, section)
    allowed = {
        "home",
        "planification",
        "programme",
        "correspondances",
        "enseignants",
        "evaluations",
        "evaluations_calendar",
        "calendrier",
        "transferts",
        "messagerie",
        "salaire",
    }
    return section if section in allowed else default


def _normalize_director_section(section: str, default: str = "home") -> str:
    """Normalize a raw section name using the same aliases as _parse_director_section."""
    aliases = {
        "operations": "planification", "assignments": "planification", "edt": "planification",
        "schedule": "planification", "planning": "planification", "academic": "programme",
        "classes": "programme", "teachers": "enseignants", "documents": "enseignants",
        "transfers": "transferts", "results": "evaluations", "publications": "evaluations",
        "settings": "enseignants", "stats": "evaluations", "notifications": "messagerie",
        "finance": "salaire",
        "logs": "evaluations", "students": "programme", "anomalies": "evaluations",
    }
    normalized = aliases.get(section, section)
    allowed = {"home", "planification", "programme", "correspondances", "enseignants", "evaluations", "evaluations_calendar", "calendrier", "transferts", "messagerie", "salaire"}
    return normalized if normalized in allowed else default


def _parse_director_week_start(request):
    raw = (request.GET.get("week_start") or request.POST.get("week_start") or "").strip()
    if raw:
        try:
            week_start = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            week_start = timezone.localdate()
    else:
        week_start = timezone.localdate()
    return week_start - timedelta(days=week_start.weekday())


def _director_classes_queryset(branch):
    qs = AcademicClass.objects.select_related("programme", "branch", "academic_year").filter(is_active=True)
    if branch:
        qs = qs.filter(branch=branch)
    return qs.annotate(student_count=Count("enrollments", filter=Q(enrollments__is_active=True))).order_by("level", "programme__title", "id")


def _director_semester_rows(branch):
    semesters = (
        Semester.objects.select_related("academic_class", "academic_class__programme", "academic_class__branch")
        .prefetch_related("ues__ecs")
        .filter(academic_class__is_active=True)
    )
    if branch:
        semesters = semesters.filter(academic_class__branch=branch)

    semester_list = list(semesters.order_by("academic_class__level", "academic_class__programme__title", "number", "id"))
    semester_ids = [s.id for s in semester_list]

    enrollments_by_class = defaultdict(list)
    if branch:
        enrollments_qs = AcademicEnrollment.objects.select_related("academic_class", "academic_year").filter(branch=branch, is_active=True)
    else:
        enrollments_qs = AcademicEnrollment.objects.select_related("academic_class", "academic_year").filter(is_active=True)
    all_enrollment_ids = []
    for enrollment in enrollments_qs:
        enrollments_by_class[enrollment.academic_class_id].append(enrollment)
        all_enrollment_ids.append(enrollment.id)

    all_ec_ids_by_semester = {}
    for semester in semester_list:
        ec_ids = []
        for ue in semester.ues.all():
            for ec in ue.ecs.all():
                ec_ids.append(ec.id)
        all_ec_ids_by_semester[semester.id] = list(dict.fromkeys(ec_ids))

    all_ec_ids_flat = list({ec_id for ids in all_ec_ids_by_semester.values() for ec_id in ids})
    grades_counts_by_semester = defaultdict(int)
    if all_ec_ids_flat and all_enrollment_ids:
        for grade in ECGrade.objects.filter(
            enrollment_id__in=all_enrollment_ids,
            ec_id__in=all_ec_ids_flat,
            final_score__isnull=False,
        ).values("enrollment__academic_class_id", "ec__ue__semester_id"):
            grades_counts_by_semester[grade["ec__ue__semester_id"]] += 1

    bulletins_counts = defaultdict(int)
    if semester_ids:
        for row in (
            AcademicBulletin.objects
            .filter(semester_id__in=semester_ids, bulletin_type=AcademicBulletin.TYPE_SEMESTER)
            .exclude(status=AcademicBulletin.STATUS_CANCELLED)
            .values("semester_id")
            .annotate(c=Count("id"))
        ):
            bulletins_counts[row["semester_id"]] = row["c"]

    rows = []
    for semester in semester_list:
        ec_ids = all_ec_ids_by_semester[semester.id]
        enrollments = enrollments_by_class.get(semester.academic_class_id, [])
        expected = len(ec_ids) * len(enrollments)
        entered = grades_counts_by_semester[semester.id] if expected else 0
        progress = int((entered / expected) * 100) if expected else 0
        ready = expected > 0 and entered >= expected
        if semester.status == Semester.STATUS_PUBLISHED:
            state = "publie"
            tone = "emerald"
        elif semester.status == Semester.STATUS_FINALIZED:
            state = "pret_publication"
            tone = "blue"
        elif ready:
            state = "pret_validation"
            tone = "emerald"
        elif entered:
            state = "en_cours"
            tone = "amber"
        else:
            state = "pas_de_notes"
            tone = "rose"
        rows.append({
            "semester": semester,
            "class": semester.academic_class,
            "student_count": len(enrollments),
            "expected": expected,
            "entered": entered,
            "progress": progress,
            "ready": ready,
            "state": state,
            "tone": tone,
            "can_validate": ready and semester.status not in {Semester.STATUS_FINALIZED, Semester.STATUS_PUBLISHED},
            "can_publish": semester.status == Semester.STATUS_FINALIZED,
            "can_generate": semester.status == Semester.STATUS_PUBLISHED,
            "bulletins_count": bulletins_counts[semester.id],
        })
    return rows


def _format_director_decimal(value):
    try:
        return f"{Decimal(str(value)):.2f}".replace(".", ",")
    except Exception:
        return "-"


_DIRECTOR_SESSION_SUBVIEWS = (
    ("overview", "Vue d'ensemble", "layout-dashboard"),
    ("sessions", "Sessions", "calendar-range"),
    ("create", "Planifier", "calendar-plus"),
    ("scheduled", "Programmées", "calendar-clock"),
)
_DIRECTOR_RESULT_SUBVIEWS = (
    ("overview", "Vue d'ensemble", "layout-dashboard"),
    ("validation", "Validation et publication", "badge-check"),
)
_DIRECTOR_PROGRAMME_SUBVIEWS = (
    ("overview", "Vue d'ensemble", "layout-dashboard"),
    ("classes", "Classes", "school"),
    ("maquettes", "Maquettes pédagogiques", "library-big"),
)
_DIRECTOR_TEACHER_SUBVIEWS = (
    ("overview", "Vue d'ensemble", "layout-dashboard"),
    ("directory", "Répertoire", "users"),
    ("assignments", "Affectations", "link-2"),
    ("files", "Dossiers", "folder-check"),
)
_DIRECTOR_DOCUMENT_SUBVIEWS = (
    ("overview", "Vue d'ensemble", "layout-dashboard"),
    ("create", "Rédiger", "file-plus-2"),
    ("archives", "Documents", "archive"),
)

_DIRECTOR_TIMETABLE_SUBVIEWS = (
    ("overview", "Vue d'ensemble", "layout-dashboard"),
    ("builder", "Construire", "calendar-plus"),
    ("preview", "Aperçu et impression", "printer"),
)

_DIRECTOR_TRANSFER_SUBVIEWS = (
    ("overview", "Vue d'ensemble", "layout-dashboard"),
    ("pending", "À traiter", "inbox"),
    ("history", "Historique", "history"),
)

_DIRECTOR_SALARY_SUBVIEWS = (
    ("overview", "Vue d'ensemble", "layout-dashboard"),
    ("history", "Historique", "history"),
)

_DIRECTOR_SUBVIEW_DEFINITIONS = {
    "planification": _DIRECTOR_TIMETABLE_SUBVIEWS,
    "evaluations_calendar": _DIRECTOR_SESSION_SUBVIEWS,
    "evaluations": _DIRECTOR_RESULT_SUBVIEWS,
    "programme": _DIRECTOR_PROGRAMME_SUBVIEWS,
    "enseignants": _DIRECTOR_TEACHER_SUBVIEWS,
    "correspondances": _DIRECTOR_DOCUMENT_SUBVIEWS,
    "transferts": _DIRECTOR_TRANSFER_SUBVIEWS,
    "salaire": _DIRECTOR_SALARY_SUBVIEWS,
}


def _director_section_subview(request, section):
    raw_view = (request.GET.get("view") or "overview").strip().lower()
    allowed = {
        item[0]
        for item in _DIRECTOR_SUBVIEW_DEFINITIONS.get(
            section, _DIRECTOR_RESULT_SUBVIEWS
        )
    }
    return raw_view if raw_view in allowed else "overview"


def _director_subnav_items(*, section, active, fragment_url_name, target, indicator):
    dashboard_url = reverse("accounts_portal:portal_dashboard")
    fragment_url = reverse(fragment_url_name)
    definitions = _DIRECTOR_SUBVIEW_DEFINITIONS.get(
        section, _DIRECTOR_RESULT_SUBVIEWS
    )
    return [
        {
            "id": item_id,
            "label": label,
            "icon": icon,
            "href": f"{dashboard_url}?section={section}&view={item_id}",
            "hx_get": f"{fragment_url}?view={item_id}",
            "hx_target": target,
            "hx_swap": "innerHTML",
            "hx_push_url": f"{dashboard_url}?section={section}&view={item_id}",
            "hx_indicator": indicator,
            "hx_sync": f"{target}:replace",
        }
        for item_id, label, icon in definitions
    ]


def _director_subview_push_url(request, *, section, subview):
    params = request.GET.copy()
    params["section"] = section
    params["view"] = subview
    return f"{reverse('accounts_portal:portal_dashboard')}?{params.urlencode()}"


def _render_director_subview(request, *, section, subview, template_name, toast=None, extra=None):
    original_get = request.GET
    params = request.GET.copy()
    params["section"] = section
    params["view"] = subview
    request.GET = params
    try:
        context = _build_director_workspace_context(request, toast=toast)
    finally:
        request.GET = original_get
    if extra:
        context.update(extra)
    context["director_fragment_response"] = True
    response = render(request, template_name, context)
    response["HX-Push-Url"] = _director_subview_push_url(
        request, section=section, subview=subview
    )
    return response


def _build_director_workspace_context(request, *, toast=None):
    branch = _resolve_director_branch(request)
    section = _parse_director_section(request)
    session_subview = _director_section_subview(request, "evaluations_calendar")
    eval_subview = _director_section_subview(request, "evaluations")
    programme_subview = _director_section_subview(request, "programme")
    teacher_subview = _director_section_subview(request, "enseignants")
    document_subview = _director_section_subview(request, "correspondances")
    timetable_subview = _director_section_subview(request, "planification")
    transfer_subview = _director_section_subview(request, "transferts")
    salary_subview = _director_section_subview(request, "salaire")
    week_start = _parse_director_week_start(request)
    week_end = week_start + timedelta(days=7)

    _NEEDS_SCHEDULE      = {"planification"}
    _NEEDS_SEMESTERS     = {"planification", "evaluations", "programme", "home"}
    _NEEDS_TEACHERS      = {"enseignants", "home"}
    _NEEDS_DOCUMENTS     = {"correspondances", "enseignants"}
    _NEEDS_TRANSFERS     = {"transferts"}
    _NEEDS_RESULTS       = {"evaluations"}
    _NEEDS_EXAM_SESSIONS = {"evaluations_calendar"}
    _NEEDS_EVAL_EVENTS   = {"evaluations_calendar"}
    _NEEDS_CALENDAR_MGT  = {"planification", "evaluations_calendar", "calendrier"}

    if section in _NEEDS_SCHEDULE and branch:
        director_overview = get_director_schedule_overview(branch, week_start)
    else:
        director_overview = {"stats": {}, "quality": {"score": 0, "warnings": []}, "alerts": [], "timetable": {"events": [], "summary": {}, "day_event_counts": []}}
    schedule_stats = director_overview.get("stats") or {}
    quality = director_overview.get("quality") or {"score": 0, "warnings": []}
    alerts = director_overview.get("alerts") or []
    timetable = director_overview.get("timetable") or {"events": [], "summary": {}, "day_event_counts": [], "empty_days": []}

    class_rows = list(_director_classes_queryset(branch))

    if section in _NEEDS_SEMESTERS:
        semester_rows = _director_semester_rows(branch)
    else:
        semester_rows = []
    semester_rows_by_class = defaultdict(list)
    for row in semester_rows:
        semester_rows_by_class[row["class"].id].append(row)

    class_cards = []
    rejected_semester_ids = {
        int(semester_id)
        for semester_id in (request.session.get("director_rejected_semester_ids") or [])
        if str(semester_id).isdigit()
    }
    for academic_class in class_rows:
        rows = semester_rows_by_class.get(academic_class.id, [])
        rejected_count = sum(1 for row in rows if row["semester"].id in rejected_semester_ids)
        ready_count = sum(1 for row in rows if row["can_validate"] or row["can_publish"])
        if rejected_count:
            workflow_bucket = "rejected"
        elif ready_count:
            workflow_bucket = "ready"
        else:
            workflow_bucket = "in_progress"
        class_cards.append({
            "class": academic_class,
            "semester_count": len(rows),
            "ready_to_validate_count": sum(1 for row in rows if row["can_validate"]),
            "ready_to_publish_count": sum(1 for row in rows if row["can_publish"]),
            "published_count": sum(1 for row in rows if row["can_generate"]),
            "rejected_count": rejected_count,
            "progress": int(sum(row["progress"] for row in rows) / len(rows)) if rows else 0,
            "student_count": academic_class.student_count,
            "workflow_bucket": workflow_bucket,
            "rows": rows,
        })

    selected_class = None
    raw_class = (request.GET.get("class_id") or request.POST.get("class_id") or "").strip()
    if raw_class.isdigit():
        class_id = int(raw_class)
        selected_class = next((item["class"] for item in class_cards if item["class"].id == class_id), None)
    if selected_class is None and section in {"academic", "students", "operations"} and class_cards:
        selected_class = class_cards[0]["class"]

    programme_context = {}
    if section == "programme":
        programme_context = build_director_programme_context(
            branch=branch,
            subview=programme_subview,
            selected_class_id=raw_class,
            query=(request.GET.get("programme_q") or "").strip(),
            programme_id=(request.GET.get("programme_id") or "").strip(),
            academic_year_id=(request.GET.get("academic_year_id") or "").strip(),
            level=(request.GET.get("level") or "").strip(),
            page_number=(request.GET.get("programme_page") or "1").strip(),
        )
        selected_class = programme_context["programme_selected_class"]

    timetable_context = {}
    if section == "planification":
        timetable_context = build_director_timetable_context(
            branch=branch,
            subview=timetable_subview,
            selected_class_id=raw_class,
            week_start=week_start,
        )

    selected_class_rows = semester_rows_by_class.get(getattr(selected_class, "id", None), []) if selected_class else []

    student_q = (request.GET.get("student_q") or request.POST.get("student_q") or "").strip()
    selected_class_students = []
    selected_class_student_count = 0
    selected_student_entry = None
    selected_class_schedule = None
    if selected_class is not None:
        student_enrollments = (
            AcademicEnrollment.objects.select_related(
                "academic_class",
                "academic_year",
                "student",
                "student__profile",
                "student__student_profile",
                "student__student_profile__inscription__candidature",
            )
            .filter(
                academic_class=selected_class,
                academic_year=selected_class.academic_year,
                is_active=True,
            )
        )
        if student_q:
            student_enrollments = student_enrollments.filter(
                Q(student__first_name__icontains=student_q)
                | Q(student__last_name__icontains=student_q)
                | Q(student__username__icontains=student_q)
                | Q(student__profile__employee_code__icontains=student_q)
                | Q(student__student_profile__matricule__icontains=student_q)
                | Q(student__student_profile__inscription__candidature__first_name__icontains=student_q)
                | Q(student__student_profile__inscription__candidature__last_name__icontains=student_q)
            )
        selected_class_student_count = student_enrollments.count()
        for enrollment in student_enrollments.order_by(
            "student__student_profile__inscription__candidature__last_name",
            "student__student_profile__inscription__candidature__first_name",
            "student__username",
        )[:40]:
            student_profile = getattr(enrollment.student, "student_profile", None)
            selected_class_students.append({
                "enrollment": enrollment,
                "student": enrollment.student,
                "full_name": getattr(student_profile, "full_name", "") or enrollment.student.get_full_name() or enrollment.student.username,
                "matricule": getattr(student_profile, "matricule", "") or "Matricule absent",
                "email": getattr(student_profile, "email", "") or enrollment.student.email or "Email absent",
                "is_enrolled": bool(getattr(student_profile, "is_enrolled", False)),
            })
        selected_class_schedule = get_class_week_schedule(selected_class, week_start)
        raw_student_id = (request.GET.get("student_id") or request.POST.get("student_id") or "").strip()
        if raw_student_id.isdigit():
            selected_student_entry = next(
                (
                    item
                    for item in selected_class_students
                    if item["student"].id == int(raw_student_id) or item["enrollment"].id == int(raw_student_id)
                ),
                None,
            )

    classroom_ops_context = build_director_classroom_ops_context(
        class_cards=class_cards,
        selected_class=selected_class,
        selected_class_rows=selected_class_rows,
        selected_class_student_count=selected_class_student_count,
        selected_class_schedule=selected_class_schedule,
    )

    teacher_load_map = schedule_stats.get("teacher_load") or {}
    class_load_map = schedule_stats.get("class_load") or {}
    teacher_q = (request.GET.get("teacher_q") or request.POST.get("teacher_q") or "").strip()
    teacher_scope = (request.GET.get("teacher_scope") or "all").strip().lower()

    if section in _NEEDS_TEACHERS:
        teacher_context = build_director_teacher_assignment_context(
            branch=branch,
            schedule_stats=schedule_stats,
            teacher_q=teacher_q,
            teacher_scope=teacher_scope,
        )
    else:
        teacher_context = {
            "teacher_rows": [], "teachers_total": 0, "teacher_assigned_count": 0,
            "teacher_unassigned_count": 0, "teacher_pending_documents": 0,
            "teacher_filtered_count": 0, "teacher_scope": "all",
        }

    teacher_rows = teacher_context["teacher_rows"]
    teacher_rows_page = paginate_queryset(request, teacher_rows, per_page=20, page_param="teachers_page")
    class_cards_page = paginate_queryset(request, class_cards, per_page=10, page_param="classes_page")

    validation_q = (request.GET.get("validation_q") or "").strip()
    validation_scope = (request.GET.get("validation_scope") or "actionable").strip().lower()
    if validation_scope not in {"actionable", "all", "ready", "rejected"}:
        validation_scope = "actionable"
    validation_cards = class_cards
    if validation_q:
        lowered_q = validation_q.casefold()
        validation_cards = [
            item
            for item in validation_cards
            if lowered_q in item["class"].display_name.casefold()
        ]
    if validation_scope == "actionable":
        validation_cards = [
            item
            for item in validation_cards
            if item["ready_to_validate_count"]
            or item["ready_to_publish_count"]
            or item["rejected_count"]
        ]
    elif validation_scope == "ready":
        validation_cards = [
            item
            for item in validation_cards
            if item["ready_to_validate_count"] or item["ready_to_publish_count"]
        ]
    elif validation_scope == "rejected":
        validation_cards = [item for item in validation_cards if item["rejected_count"]]
    validation_class_cards_page = paginate_queryset(
        request,
        validation_cards,
        per_page=10,
        page_param="classes_page",
    )
    validation_query_suffix = (
        f"view=validation&validation_scope={quote(validation_scope)}"
        f"&validation_q={quote(validation_q)}"
    )
    teachers_query_suffix = (
        f"view={quote(teacher_subview)}&teacher_q={quote(teacher_q)}"
        f"&teacher_scope={quote(teacher_context['teacher_scope'])}"
    )
    classes_query_suffix = "section=evaluations"

    class_load_items = sorted(
        (class_load_map or {}).items(),
        key=lambda item: (-item[1]["hours"], item[0]),
    )[:5]
    teacher_load_items = sorted(
        (teacher_load_map or {}).items(),
        key=lambda item: (-item[1]["hours"], item[0]),
    )[:5]

    selected_semester = None
    selected_semester_row = None
    raw_semester = (request.GET.get("semester_id") or request.POST.get("semester_id") or "").strip()
    if raw_semester.isdigit():
        selected_semester_row = next((row for row in semester_rows if row["semester"].id == int(raw_semester)), None)
        if selected_semester_row:
            selected_semester = selected_semester_row["semester"]
    if selected_semester_row and selected_class and selected_semester_row["class"].id != selected_class.id:
        selected_semester_row = None
        selected_semester = None
    if selected_semester is None and section == "results" and selected_class_rows:
        preferred = next((row for row in selected_class_rows if row["can_validate"] or row["can_publish"]), selected_class_rows[0])
        selected_semester_row = preferred
        selected_semester = preferred["semester"]

    results_class_queues = {
        "ready": [item for item in class_cards if item["workflow_bucket"] == "ready"],
        "in_progress": [item for item in class_cards if item["workflow_bucket"] == "in_progress"],
        "rejected": [item for item in class_cards if item["workflow_bucket"] == "rejected"],
    }
    results_query_suffix = (
        f"section=results&class_id={selected_class.id}&semester_id={selected_semester.id}"
        if selected_class is not None and selected_semester is not None
        else "section=results"
    )
    result_table_rows = []
    result_anomalies = []
    result_summary = None
    if selected_semester is not None:
        semester_enrollments = list(
            AcademicEnrollment.objects.select_related(
                "student",
                "student__student_profile",
                "student__student_profile__inscription__candidature",
                "academic_class",
                "academic_year",
            ).filter(
                academic_class=selected_semester.academic_class,
                academic_year=selected_semester.academic_class.academic_year,
                is_active=True,
            )
        )
        ec_ids = list(selected_semester.ues.values_list("ecs__id", flat=True).distinct())
        ec_ids = [ec_id for ec_id in ec_ids if ec_id is not None]
        grades_by_enrollment = defaultdict(dict)
        for grade in ECGrade.objects.filter(enrollment__in=semester_enrollments, ec_id__in=ec_ids).select_related("ec"):
            grades_by_enrollment[grade.enrollment_id][grade.ec_id] = grade
        ranking_rows = []
        total_average = Decimal("0.00")
        average_count = 0
        completed_students = 0
        for enrollment in semester_enrollments:
            threshold = resolve_threshold(enrollment)
            student_profile = getattr(enrollment.student, "student_profile", None)
            student_name = getattr(student_profile, "full_name", "") or enrollment.student.get_full_name() or enrollment.student.username
            grade_map = grades_by_enrollment.get(enrollment.id, {})
            missing_count = sum(1 for ec_id in ec_ids if grade_map.get(ec_id) is None or grade_map[ec_id].final_score is None)
            semester_result = compute_semester_result(selected_semester, enrollment)
            average = semester_result["average"]
            if average is not None:
                total_average += Decimal(str(average))
                average_count += 1
            if missing_count == 0:
                completed_students += 1
            if missing_count:
                result_anomalies.append({
                    "level": "blocking",
                    "student": student_name,
                    "message": f"{missing_count} note(s) manquante(s) sur {len(ec_ids)}.",
                })
            elif average < threshold:
                result_anomalies.append({
                    "level": "attention",
                    "student": student_name,
                    "message": f"Moyenne sous le seuil ({_format_director_decimal(average)}/{_format_director_decimal(threshold)}).",
                })
            ranking_rows.append({
                "enrollment": enrollment,
                "result": semester_result,
                "missing_count": missing_count,
                "threshold": threshold,
                "student_name": student_name,
            })

        ranking_rows.sort(
            key=lambda item: (
                item["missing_count"] > 0,
                -(Decimal(str(item["result"]["average"])) if item["result"]["average"] is not None else Decimal("0.00")),
                item["student_name"],
            )
        )
        for index, item in enumerate(ranking_rows, start=1):
            enrollment = item["enrollment"]
            semester_result = item["result"]
            student_profile = getattr(enrollment.student, "student_profile", None)
            average = semester_result["average"]
            result_table_rows.append({
                "rank": index,
                "student_name": getattr(student_profile, "full_name", "") or enrollment.student.get_full_name() or enrollment.student.username,
                "matricule": getattr(student_profile, "matricule", "") or "-",
                "average": _format_director_decimal(average),
                "credits": f"{_format_director_decimal(semester_result['credit_obtained'])}/{_format_director_decimal(semester_result['credit_required'])}",
                "completion": f"{len(ec_ids) - item['missing_count']}/{len(ec_ids)}",
                "status": "Bloque" if item["missing_count"] else ("Valide" if semester_result["is_validated"] else "A surveiller"),
                "status_tone": "rose" if item["missing_count"] else ("emerald" if semester_result["is_validated"] else "amber"),
            })
        result_summary = {
            "student_count": len(semester_enrollments),
            "completed_students": completed_students,
            "blocked_students": len(semester_enrollments) - completed_students,
            "class_average": _format_director_decimal(total_average / average_count) if average_count else "-",
            "anomalies_count": len(result_anomalies),
        }

    result_anomalies_page = paginate_queryset(request, result_anomalies, per_page=12, page_param="anomalies_page")
    result_table_rows_page = paginate_queryset(request, result_table_rows, per_page=25, page_param="results_page")

    ready_to_publish = [row for row in semester_rows if row["can_publish"]]
    ready_to_validate = [row for row in semester_rows if row["can_validate"]]
    in_progress = [row for row in semester_rows if row["state"] == "en_cours"]
    without_notes = [row for row in semester_rows if row["state"] == "pas_de_notes"]
    published = [row for row in semester_rows if row["can_generate"]]
    diploma_candidate_classes = []
    if section in _NEEDS_RESULTS:
        terminal_class_ids = [
            item["class"].id for item in class_cards
            if str(item["class"].level or "").upper().strip() in {"L3", "M2"}
            and item["semester_count"] and item["published_count"] >= item["semester_count"]
        ]
        if terminal_class_ids:
            awards_counts = dict(
                AcademicDiplomaAward.objects
                .filter(academic_class_id__in=terminal_class_ids)
                .exclude(status=AcademicDiplomaAward.STATUS_CANCELLED)
                .values_list("academic_class_id")
                .annotate(c=Count("id"))
                .values_list("academic_class_id", "c")
            )
            for item in class_cards:
                academic_class = item["class"]
                if academic_class.id not in terminal_class_ids:
                    continue
                diploma_candidate_classes.append({
                    "class": academic_class,
                    "student_count": item["student_count"],
                    "awards_count": awards_counts.get(academic_class.id, 0),
                })
    document_workflows = [
        {
            "title": "Contrats enseignants",
            "summary": "Generer et suivre les contrats pedagogiques des enseignants.",
            "status": "backend_a_implanter",
            "tone": "amber",
        },
        {
            "title": "Dossiers enseignants",
            "summary": "Uploader, verifier et centraliser les pieces administratives.",
            "status": "backend_a_implanter",
            "tone": "blue",
        },
        {
            "title": "Transferts classe / ecole",
            "summary": "Constituer, valider et transmettre les dossiers de transfert.",
            "status": "backend_a_implanter",
            "tone": "rose",
        },
    ]
    assignments_alerts = [
        alert
        for alert in alerts
        if alert.get("type") in {
            "missing_teacher",
            "missing_location",
            "teacher_overload",
            "high_cancellation_rate",
            "unresolved_conflict",
            "class_without_events",
        }
    ]
    upcoming_events = list((timetable.get("events") or [])[:8])
    recent_lesson_logs = []
    if (section in _NEEDS_SCHEDULE or section == "home") and branch:
        recent_lesson_logs = list(
            LessonLog.objects.select_related(
                "academic_class",
                "ec",
                "teacher",
                "branch",
            )
            .filter(branch=branch)
            .order_by("-date", "-start_time", "-id")[:8]
        )

    raw_document_teacher = (request.GET.get("teacher_id") or request.POST.get("teacher_id") or "").strip()
    document_teacher_id = int(raw_document_teacher) if raw_document_teacher.isdigit() else None
    if section in _NEEDS_DOCUMENTS:
        document_context = build_director_document_context(
            branch=branch,
            teacher_id=document_teacher_id,
        )
    else:
        document_context = {"document_teacher_rows": [], "selected_document_teacher": None, "teacher_documents": [], "teacher_document_type_choices": []}

    transfer_q = (request.GET.get("transfer_q") or "").strip()
    transfer_type_filter = (request.GET.get("transfer_type") or "").strip()
    if section in _NEEDS_TRANSFERS:
        transfer_context = build_director_transfer_context(
            branch=branch,
            scope=transfer_subview,
            query=transfer_q,
            transfer_type=transfer_type_filter,
        )
    else:
        transfer_context = {
            "transfer_enrollments": [], "transfer_rows": [],
            "transfer_target_classes": [], "transfer_type_choices": [],
            "transfer_metrics": {}, "transfer_q": "", "transfer_type_filter": "",
        }
    transfer_rows_page = paginate_queryset(
        request, transfer_context["transfer_rows"], per_page=12, page_param="transfer_page"
    )

    salary_context = build_director_salary_context(
        user=request.user,
        branch=branch if section == "salaire" else None,
        period_month=request.GET.get("period") or request.POST.get("period"),
    )
    salary_history_page = paginate_queryset(
        request,
        salary_context["salary_history_rows"],
        per_page=15,
        page_param="salary_page",
    )

    teacher_form_ecs = list(
        EC.objects.select_related("ue", "ue__semester", "ue__semester__academic_class")
        .filter(ue__semester__academic_class__branch=branch, ue__semester__academic_class__is_active=True)
        .order_by("ue__semester__academic_class__level", "ue__semester__academic_class__programme__title", "title", "id")[:200]
    ) if (section in _NEEDS_TEACHERS and branch) else []

    planning_assignment_context = build_director_planning_assignment_context(
        assignments_alerts=assignments_alerts,
        class_load_items=class_load_items,
        teacher_load_items=teacher_load_items,
        upcoming_events=upcoming_events,
        recent_lesson_logs=recent_lesson_logs,
    )
    bulletin_scope_class = selected_class or (class_rows[0] if class_rows else None)

    # Formulaires bornés à la classe et à l'annexe courantes.
    programme_ue_rows = programme_context.get("programme_structure_rows", [])
    programme_semester_form = DirectorSemesterForm(
        branch=branch, academic_class=selected_class
    )
    programme_ue_form = DirectorUEForm(branch=branch, academic_class=selected_class)
    programme_ec_form = DirectorECForm(branch=branch, academic_class=selected_class)

    admin_documents = list(
        AdministrativeDocument.objects.filter(branch=branch).order_by("-created_at")[:50]
    ) if ((section in _NEEDS_DOCUMENTS or section == "home") and branch) else []
    admin_doc_type_choices = AdministrativeDocument.TYPE_CHOICES
    if section == "correspondances":
        administrative_document_context = build_director_administrative_document_context(
            branch=branch,
            subview=document_subview,
            query=(request.GET.get("document_q") or "").strip(),
            status=(request.GET.get("document_status") or "").strip(),
            document_type=(request.GET.get("document_type") or "").strip(),
            page_number=(request.GET.get("documents_page") or "1").strip(),
            selected_document_id=(request.GET.get("document_id") or "").strip(),
        )
    else:
        administrative_document_context = {
            "administrative_documents_page": paginate_queryset(
                request, [], per_page=12, page_param="documents_page"
            ),
            "administrative_document_metrics": {"total": 0, "draft": 0, "published": 0},
            "administrative_document_selected": None,
            "administrative_document_filtered_count": 0,
            "administrative_document_q": "",
            "administrative_document_status": "",
            "administrative_document_type": "",
            "administrative_document_query_suffix": "view=archives",
            "administrative_document_type_choices": AdministrativeDocument.TYPE_CHOICES,
            "administrative_document_status_choices": AdministrativeDocument.STATUS_CHOICES,
        }
    administrative_document_form = DirectorAdministrativeDocumentForm(
        instance=administrative_document_context["administrative_document_selected"]
    )

    if section in _NEEDS_EXAM_SESSIONS:
        exam_sessions_context = build_director_exam_sessions_context(
            branch=branch,
            class_cards=class_cards,
        )
    else:
        exam_sessions_context = {
            "exam_sessions": [], "exam_session_rows": [], "upcoming_exam_sessions": [],
            "exam_sessions_by_class": [], "exam_session_classes": [],
            "exam_session_type_choices": [], "exam_session_total": 0,
            "exam_session_upcoming_count": 0,
        }

    session_q = (request.GET.get("session_q") or "").strip()
    session_type = (request.GET.get("session_type") or "").strip()
    session_status = (request.GET.get("session_status") or "").strip()
    filtered_session_rows = exam_sessions_context["exam_session_rows"]
    if session_q:
        lowered_q = session_q.casefold()
        filtered_session_rows = [
            row
            for row in filtered_session_rows
            if lowered_q in row["entry"].title.casefold()
            or lowered_q in row["type_label"].casefold()
        ]
    if session_type:
        filtered_session_rows = [
            row for row in filtered_session_rows if row["entry"].event_type == session_type
        ]
    if session_status:
        filtered_session_rows = [
            row for row in filtered_session_rows if row["state"] == session_status
        ]
    exam_session_rows_page = paginate_queryset(
        request,
        filtered_session_rows,
        per_page=8,
        page_param="sessions_page",
    )
    session_query_suffix = (
        f"view=sessions&session_q={quote(session_q)}"
        f"&session_type={quote(session_type)}&session_status={quote(session_status)}"
    )

    # ── Evaluations planifiées (AcademicScheduleEvent type exam/practical) ───
    if section in _NEEDS_EVAL_EVENTS and branch:
        now = timezone.now()
        evaluation_events = (
            AcademicScheduleEvent.objects.select_related(
                "academic_class",
                "academic_class__programme",
                "ec",
                "ec__ue",
                "teacher",
            )
            .filter(
                branch=branch,
                event_type__in=[
                    AcademicScheduleEvent.EVENT_TYPE_EXAM,
                    AcademicScheduleEvent.EVENT_TYPE_PRACTICAL,
                ],
                is_active=True,
            )
            .order_by("start_datetime", "id")
        )
        eval_event_total = evaluation_events.count()
        eval_event_upcoming_count = (
            evaluation_events.exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
            .filter(start_datetime__gte=now)
            .count()
        )

        evaluation_q = (request.GET.get("evaluation_q") or "").strip()
        evaluation_status = (request.GET.get("evaluation_status") or "").strip()
        evaluation_type = (request.GET.get("evaluation_type") or "").strip()
        raw_evaluation_class = (request.GET.get("evaluation_class") or "").strip()
        filtered_events = evaluation_events
        if evaluation_q:
            filtered_events = filtered_events.filter(
                Q(title__icontains=evaluation_q)
                | Q(ec__title__icontains=evaluation_q)
                | Q(academic_class__name__icontains=evaluation_q)
                | Q(academic_class__programme__title__icontains=evaluation_q)
                | Q(location__icontains=evaluation_q)
            )
        if evaluation_status in dict(AcademicScheduleEvent.STATUS_CHOICES):
            filtered_events = filtered_events.filter(status=evaluation_status)
        else:
            evaluation_status = ""
        allowed_evaluation_types = {
            AcademicScheduleEvent.EVENT_TYPE_EXAM,
            AcademicScheduleEvent.EVENT_TYPE_PRACTICAL,
        }
        if evaluation_type in allowed_evaluation_types:
            filtered_events = filtered_events.filter(event_type=evaluation_type)
        else:
            evaluation_type = ""
        if raw_evaluation_class.isdigit():
            filtered_events = filtered_events.filter(
                academic_class_id=int(raw_evaluation_class)
            )
        else:
            raw_evaluation_class = ""

        eval_events_page = paginate_queryset(
            request,
            filtered_events,
            per_page=10,
            page_param="events_page",
        )
        eval_by_class = {}
        for evt in eval_events_page.object_list:
            class_id = evt.academic_class_id
            if class_id not in eval_by_class:
                eval_by_class[class_id] = {
                    "academic_class": evt.academic_class,
                    "events": [],
                }
            eval_by_class[class_id]["events"].append(evt)
        eval_events_by_class = list(eval_by_class.values())
        evaluation_query_suffix = (
            f"view=scheduled&evaluation_q={quote(evaluation_q)}"
            f"&evaluation_status={quote(evaluation_status)}"
            f"&evaluation_type={quote(evaluation_type)}"
            f"&evaluation_class={quote(raw_evaluation_class)}"
        )
    else:
        eval_events_by_class = []
        eval_event_upcoming_count = 0
        eval_event_total = 0
        eval_events_page = paginate_queryset(
            request, [], per_page=10, page_param="events_page"
        )
        evaluation_q = ""
        evaluation_status = ""
        evaluation_type = ""
        raw_evaluation_class = ""
        evaluation_query_suffix = "view=scheduled"

    evaluation_form = DirectorEvaluationForm(
        branch=branch,
        selected_class_id=(request.GET.get("class_id") or "").strip(),
    )
    exam_session_form = DirectorExamSessionForm(
        event_type_choices=exam_sessions_context["exam_session_type_choices"],
    )

    if section in _NEEDS_CALENDAR_MGT and branch:
        raw_cal_id = (request.GET.get("calendar_id") or request.POST.get("calendar_id") or "").strip()
        selected_cal_id = int(raw_cal_id) if raw_cal_id.isdigit() else None
        calendar_ctx = build_director_calendar_context(branch, selected_calendar_id=selected_cal_id)
    else:
        calendar_ctx = {
            "director_all_academic_years": [],
            "director_active_academic_year": None,
            "director_academic_calendars": [],
            "director_selected_calendar": None,
            "director_calendar_entries": [],
            "director_calendar_entry_count": 0,
            "director_calendar_can_validate": False,
            "director_calendar_can_publish": False,
            "director_calendar_can_add_entry": False,
            "director_calendar_entry_type_counts": {},
            "director_calendar_event_type_choices": [],
        }

    context = {
        "branch": branch,
        "director_global_scope": bool(is_global_academic_user(request.user) and branch is None),
        "section": section,
        "session_subview": session_subview,
        "eval_subview": eval_subview,
        "programme_subview": programme_subview,
        "teacher_subview": teacher_subview,
        "document_subview": document_subview,
        "timetable_subview": timetable_subview,
        "transfer_subview": transfer_subview,
        "salary_subview": salary_subview,
        "session_tabs": _director_subnav_items(
            section="evaluations_calendar",
            active=session_subview,
            fragment_url_name="accounts_portal:director_exam_sessions_subcontent",
            target="#director-session-subcontent",
            indicator="#director-session-loading",
        ),
        "result_tabs": _director_subnav_items(
            section="evaluations",
            active=eval_subview,
            fragment_url_name="accounts_portal:director_evaluations_subcontent",
            target="#director-results-subcontent",
            indicator="#director-results-loading",
        ),
        "programme_tabs": _director_subnav_items(
            section="programme",
            active=programme_subview,
            fragment_url_name="accounts_portal:director_programme_subcontent",
            target="#director-programme-subcontent",
            indicator="#director-programme-loading",
        ),
        "teacher_tabs": _director_subnav_items(
            section="enseignants",
            active=teacher_subview,
            fragment_url_name="accounts_portal:director_teachers_subcontent",
            target="#director-teacher-subcontent",
            indicator="#director-teacher-loading",
        ),
        "document_tabs": _director_subnav_items(
            section="correspondances",
            active=document_subview,
            fragment_url_name="accounts_portal:director_documents_subcontent",
            target="#director-document-subcontent",
            indicator="#director-document-loading",
        ),
        "timetable_tabs": _director_subnav_items(
            section="planification",
            active=timetable_subview,
            fragment_url_name="accounts_portal:director_timetable_subcontent",
            target="#director-timetable-subcontent",
            indicator="#director-timetable-loading",
        ),
        "transfer_tabs": _director_subnav_items(
            section="transferts",
            active=transfer_subview,
            fragment_url_name="accounts_portal:director_transfers_subcontent",
            target="#director-transfer-subcontent",
            indicator="#director-transfer-loading",
        ),
        "salary_tabs": _director_subnav_items(
            section="salaire",
            active=salary_subview,
            fragment_url_name="accounts_portal:director_salary_subcontent",
            target="#director-salary-subcontent",
            indicator="#director-salary-loading",
        ),
        "week_start": week_start,
        "week_end": week_end,
        "prev_week_start": week_start - timedelta(days=7),
        "next_week_start": week_start + timedelta(days=7),
        "director_overview": director_overview,
        "schedule_stats": schedule_stats,
        "quality": quality,
        "alerts": alerts,
        "timetable": timetable,
        "class_load_items": class_load_items,
        "teacher_load_items": teacher_load_items,
        "today": timezone.localdate(),
        "classes": class_rows,
        "class_cards": class_cards,
        "class_cards_page": class_cards_page,
        "validation_class_cards_page": validation_class_cards_page,
        "validation_q": validation_q,
        "validation_scope": validation_scope,
        "validation_query_suffix": validation_query_suffix,
        "validation_filtered_count": len(validation_cards),
        "validation_actionable_count": sum(
            1
            for item in class_cards
            if item["ready_to_validate_count"]
            or item["ready_to_publish_count"]
            or item["rejected_count"]
        ),
        "classes_query_suffix": classes_query_suffix,
        "total_classes": len(class_rows),
        "total_semesters": len(semester_rows),
        "semester_rows": semester_rows,
        "ready_to_publish": ready_to_publish,
        "ready_to_validate": ready_to_validate,
        "in_progress": in_progress,
        "without_notes": without_notes,
        "published": published,
        "can_manage_bulletins": bool(bulletin_scope_class and can_manage_bulletins(request.user, bulletin_scope_class)),
        "can_manage_diplomas": get_user_position(request.user) in {"executive_director", "deputy_executive_director"},
        "diploma_candidate_classes": diploma_candidate_classes,
        "ready_to_validate_count": len(ready_to_validate),
        "published_count": len(published),
        "document_workflows": document_workflows,
        "document_teacher_rows": document_context["document_teacher_rows"],
        "selected_document_teacher": document_context["selected_document_teacher"],
        "teacher_documents": document_context["teacher_documents"],
        "teacher_document_type_choices": document_context["teacher_document_type_choices"],
        "transfer_enrollments": transfer_context["transfer_enrollments"],
        "transfer_rows": transfer_context["transfer_rows"],
        "transfer_rows_page": transfer_rows_page,
        "transfer_target_classes": transfer_context["transfer_target_classes"],
        "transfer_type_choices": transfer_context["transfer_type_choices"],
        "transfer_metrics": transfer_context["transfer_metrics"],
        "transfer_q": transfer_context["transfer_q"],
        "transfer_type_filter": transfer_context["transfer_type_filter"],
        "transfer_query_suffix": (
            f"view={quote(transfer_subview)}&transfer_q={quote(transfer_context['transfer_q'])}"
            f"&transfer_type={quote(transfer_context['transfer_type_filter'])}"
        ),
        "salary_query_suffix": (
            f"view={quote(salary_subview)}&period={salary_context['salary_period_value']}"
        ),
        "salary_history_page": salary_history_page,
        **salary_context,
        "teachers": teacher_rows,
        "teacher_rows_page": teacher_rows_page,
        "teachers_query_suffix": teachers_query_suffix,
        "teachers_total": teacher_context["teachers_total"],
        "teacher_unassigned_count": teacher_context["teacher_unassigned_count"],
        "teacher_assigned_count": teacher_context["teacher_assigned_count"],
        "teacher_pending_documents": teacher_context["teacher_pending_documents"],
        "teacher_filtered_count": teacher_context["teacher_filtered_count"],
        "teacher_scope": teacher_context["teacher_scope"],
        "teacher_q": teacher_q,
        "teacher_form_classes": class_rows,
        "teacher_form_ecs": teacher_form_ecs,
        "selected_semester": selected_semester,
        "selected_semester_row": selected_semester_row,
        "selected_class": selected_class,
        "selected_class_rows": selected_class_rows,
        "selected_class_students": selected_class_students,
        "selected_class_student_count": selected_class_student_count,
        "selected_class_schedule": selected_class_schedule,
        "selected_student_entry": selected_student_entry,
        "result_panel_title": (
            f"{selected_class.display_name} · Semestre {selected_semester.number}"
            if selected_class is not None and selected_semester is not None
            else "Validation semestre"
        ),
        "result_panel_subtitle": (
            f"{selected_semester_row['entered']}/{selected_semester_row['expected']} notes · {selected_semester.get_status_display()}"
            if selected_semester_row is not None and selected_semester is not None
            else "Verifier les anomalies puis decider."
        ),
        "operation_class_rows": classroom_ops_context["operation_class_rows"],
        "selected_operation_class": classroom_ops_context["selected_operation_class"],
        "selected_operation_class_id": (
            classroom_ops_context["selected_operation_class"]["class"].id
            if classroom_ops_context["selected_operation_class"]
            else None
        ),
        "student_q": student_q,
        "assignments_alerts": assignments_alerts,
        "assignments_alerts_count": len(assignments_alerts),
        "upcoming_events": upcoming_events,
        "recent_lesson_logs": recent_lesson_logs,
        "assignment_alert_rows": planning_assignment_context["assignment_alert_rows"],
        "assignment_class_rows": planning_assignment_context["assignment_class_rows"],
        "assignment_teacher_rows": planning_assignment_context["assignment_teacher_rows"],
        "assignment_event_rows": planning_assignment_context["assignment_event_rows"],
        "assignment_log_rows": planning_assignment_context["assignment_log_rows"],
        "assignment_critical_count": planning_assignment_context["assignment_critical_count"],
        "assignment_missing_teacher_count": planning_assignment_context["assignment_missing_teacher_count"],
        "assignment_missing_room_count": planning_assignment_context["assignment_missing_room_count"],
        "assignment_teacher_overload_count": planning_assignment_context["assignment_teacher_overload_count"],
        "semester_rows_by_class": semester_rows_by_class,
        "results_class_queues": results_class_queues,
        "result_table_rows": result_table_rows,
        "result_table_rows_page": result_table_rows_page,
        "result_anomalies": result_anomalies,
        "result_anomalies_page": result_anomalies_page,
        "result_summary": result_summary,
        "results_query_suffix": results_query_suffix,
        "tasks_center": build_director_tasks_center(
            branch=branch,
            semester_rows=semester_rows,
            teacher_unassigned_count=teacher_context["teacher_unassigned_count"],
            result_anomalies=result_anomalies,
        ),
        "student_panel_subtitle": (
            f"{selected_student_entry['matricule']} · {selected_student_entry['email']}"
            if selected_student_entry is not None
            else "Fiche etudiant"
        ),
        "programme_ue_rows": programme_ue_rows,
        "programme_semester_form": programme_semester_form,
        "programme_ue_form": programme_ue_form,
        "programme_ec_form": programme_ec_form,
        "admin_documents": admin_documents,
        "admin_doc_type_choices": admin_doc_type_choices,
        "admin_doc_draft_count": sum(1 for d in admin_documents if d.status == AdministrativeDocument.STATUS_DRAFT),
        "admin_doc_published_count": sum(1 for d in admin_documents if d.status == AdministrativeDocument.STATUS_PUBLISHED),
        "administrative_document_form": administrative_document_form,
        "exam_session_rows": exam_sessions_context["exam_session_rows"],
        "exam_session_rows_page": exam_session_rows_page,
        "session_q": session_q,
        "session_type": session_type,
        "session_status": session_status,
        "session_query_suffix": session_query_suffix,
        "session_filtered_count": len(filtered_session_rows),
        "upcoming_exam_sessions": exam_sessions_context["upcoming_exam_sessions"],
        "exam_sessions_by_class": exam_sessions_context["exam_sessions_by_class"],
        "exam_session_classes": exam_sessions_context["exam_session_classes"],
        "exam_session_type_choices": exam_sessions_context["exam_session_type_choices"],
        "exam_session_total": exam_sessions_context["exam_session_total"],
        "exam_session_upcoming_count": exam_sessions_context["exam_session_upcoming_count"],
        "eval_events_by_class": eval_events_by_class,
        "eval_events_page": eval_events_page,
        "eval_event_upcoming_count": eval_event_upcoming_count,
        "eval_event_total": eval_event_total,
        "evaluation_form": evaluation_form,
        "exam_session_form": exam_session_form,
        "evaluation_q": evaluation_q,
        "evaluation_status": evaluation_status,
        "evaluation_type": evaluation_type,
        "evaluation_class": raw_evaluation_class,
        "evaluation_query_suffix": evaluation_query_suffix,
        "evaluation_status_choices": AcademicScheduleEvent.STATUS_CHOICES,
        "evaluation_type_choices": (
            (AcademicScheduleEvent.EVENT_TYPE_EXAM, "Examen"),
            (AcademicScheduleEvent.EVENT_TYPE_PRACTICAL, "Évaluation pratique"),
        ),
        **calendar_ctx,
        **programme_context,
        **administrative_document_context,
        **timetable_context,
    }
    timetable_selected = context.get("timetable_selected_class")
    for item in context["timetable_tabs"]:
        if timetable_selected is not None:
            item["href"] = f"{item['href']}&class_id={timetable_selected.pk}"
            item["hx_get"] = f"{item['hx_get']}&class_id={timetable_selected.pk}"
            item["hx_push_url"] = (
                f"{item['hx_push_url']}&class_id={timetable_selected.pk}"
            )
        item["href"] = f"{item['href']}&week_start={week_start.isoformat()}"
        item["hx_get"] = f"{item['hx_get']}&week_start={week_start.isoformat()}"
        item["hx_push_url"] = (
            f"{item['hx_push_url']}&week_start={week_start.isoformat()}"
        )
    if toast:
        context["toast"] = toast
    return context


def _director_account_profile_context(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    position = get_user_position(request.user)
    position_label = dict(Profile.POSITION_CHOICES).get(profile.position, profile.position or "")
    role_label = dict(Profile.ROLE_CHOICES).get(profile.role, profile.role or "")
    status_label = dict(Profile.EMPLOYMENT_STATUS_CHOICES).get(profile.employment_status, profile.employment_status or "")
    extra_fields = []
    if profile.employee_code:
        extra_fields.append({"label": "Code employe", "value": profile.employee_code})
    if profile.location:
        extra_fields.append({"label": "Localisation", "value": profile.location})
    if profile.main_domain:
        extra_fields.append({"label": "Domaine", "value": profile.main_domain})
    if profile.website:
        extra_fields.append({"label": "Site web", "value": profile.website})
    if position_label:
        extra_fields.append({"label": "Fonction", "value": position_label})
    if role_label:
        extra_fields.append({"label": "Groupe", "value": role_label})
    account_actions = [
        {
            "label": "Modifier",
            "icon": "pencil",
            "hx_get": f"{reverse('accounts_portal:director_account_panel')}?view=edit",
            "hx_target": "#director-drawer-content",
            "hx_swap": "innerHTML",
        },
        {
            "label": "Securite",
            "icon": "shield",
            "hx_get": f"{reverse('accounts_portal:director_account_panel')}?view=security",
            "hx_target": "#director-drawer-content",
            "hx_swap": "innerHTML",
        },
        {
            "label": "Preferences",
            "icon": "settings",
            "hx_get": f"{reverse('accounts_portal:director_account_panel')}?view=preferences",
            "hx_target": "#director-drawer-content",
            "hx_swap": "innerHTML",
        },
    ]
    return {
        "profile": profile,
        "display_name": request.user.get_full_name() or request.user.username,
        "avatar_url": profile.avatar_url,
        "email": request.user.email,
        "role": position_label or role_label or "Compte institutionnel",
        "branch": profile.branch.name if profile.branch else "Annexe non definie",
        "status": profile.employment_status,
        "status_label": status_label or "Actif",
        "phone": profile.phone,
        "address": profile.address,
        "created_at": timezone.localtime(profile.created_at).strftime("%d/%m/%Y") if profile.created_at else "",
        "last_seen": timezone.localtime(profile.last_seen).strftime("%d/%m/%Y %H:%M") if profile.last_seen else "",
        "bio": profile.bio,
        "extra_fields": extra_fields,
        "account_actions": account_actions,
        "is_system_account": bool(position),
    }


def _director_notifications_items(request, notifications):
    items = []
    for notification in notifications:
        created_at = timezone.localtime(notification.created_at).strftime("%d/%m/%Y %H:%M") if notification.created_at else ""
        if notification.event_type == "internal_message" and notification.actor_id == request.user.pk:
            source_label = f"À {notification.recipient.get_full_name() or notification.recipient.username}"
        elif notification.actor:
            source_label = f"De {notification.actor.get_full_name() or notification.actor.username}"
        else:
            source_label = notification.event_type or notification.legacy_source or "Système"
        items.append({
            "id": notification.id,
            "title": notification.title,
            "summary": notification.body[:140] if notification.body else "",
            "icon": "bell",
            "source": source_label,
            "time_ago": created_at,
            "is_read": notification.read_at is not None,
            "priority": notification.priority,
            "sender": (
                notification.actor.get_full_name() or notification.actor.username
                if notification.actor else "Système"
            ),
            "recipient": (
                notification.recipient.get_full_name() or notification.recipient.username
                if notification.recipient else "Destinataire externe"
            ),
            "action_url": get_safe_action_url(notification, request),
            "detail_url": reverse("accounts_portal:director_notification_detail", args=[notification.id]),
            "hx_mark_read": "",
        })
    return items


def _director_notifications_context(request):
    box = (request.GET.get("box") or request.POST.get("box") or "inbox").strip().lower()
    if box not in {"inbox", "sent", "archived", "trash"}:
        box = "inbox"
    filters = {
        "channel": request.GET.get("channel") or "in_app",
        "status": request.GET.get("status") or "",
        "priority": request.GET.get("priority") or "",
        "source": request.GET.get("source") or "",
        "q": (request.GET.get("q") or "").strip(),
    }
    if box == "sent":
        queryset = NotificationMessage.objects.select_related("actor", "recipient", "event").filter(
            actor=request.user,
            event_type="internal_message",
            channel=NotificationMessage.CHANNEL_IN_APP,
            deleted_at__isnull=True,
        )
        if filters["q"]:
            queryset = queryset.filter(
                Q(title__icontains=filters["q"])
                | Q(body__icontains=filters["q"])
                | Q(recipient__first_name__icontains=filters["q"])
                | Q(recipient__last_name__icontains=filters["q"])
                | Q(recipient__username__icontains=filters["q"])
            )
    elif box == "trash":
        queryset = NotificationMessage.objects.select_related("actor", "recipient", "event").filter(
            recipient=request.user,
            channel=NotificationMessage.CHANNEL_IN_APP,
            deleted_at__isnull=False,
        )
        if filters["q"]:
            queryset = queryset.filter(Q(title__icontains=filters["q"]) | Q(body__icontains=filters["q"]))
    else:
        if box == "archived":
            filters["status"] = "archived"
        queryset = get_notification_center_queryset(request.user, filters)
    queryset = queryset.order_by("-pinned_at", "-created_at")
    paginator = Paginator(queryset, 10)
    page = request.GET.get("page") or 1
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages or 1)

    selected_notification = None
    selected_id = (request.GET.get("notification_id") or "").strip()
    if selected_id.isdigit():
        selected_queryset = NotificationMessage.objects.select_related("actor", "recipient", "event").filter(pk=int(selected_id))
        if box == "sent":
            selected_queryset = selected_queryset.filter(
                actor=request.user,
                event_type="internal_message",
                channel=NotificationMessage.CHANNEL_IN_APP,
            )
        elif box == "trash":
            selected_queryset = selected_queryset.filter(recipient=request.user, deleted_at__isnull=False)
        else:
            selected_queryset = selected_queryset.filter(recipient=request.user)
        selected_notification = selected_queryset.first()
    if selected_notification is None and page_obj.object_list:
        selected_notification = page_obj.object_list[0]
    if (
        box == "inbox"
        and selected_notification is not None
        and selected_notification.recipient_id == request.user.pk
        and selected_notification.channel == NotificationMessage.CHANNEL_IN_APP
        and selected_notification.read_at is None
    ):
        NotificationBus.mark_as_read(selected_notification)

    stats = get_notification_center_stats(request.user)
    stats["sent"] = NotificationMessage.objects.filter(
        actor=request.user,
        event_type="internal_message",
        channel=NotificationMessage.CHANNEL_IN_APP,
        deleted_at__isnull=True,
    ).count()
    stats["trash"] = NotificationMessage.objects.filter(
        recipient=request.user,
        channel=NotificationMessage.CHANNEL_IN_APP,
        deleted_at__isnull=False,
    ).count()
    selected_attachments = MessageAttachment.objects.none()
    selected_thread = NotificationMessage.objects.none()
    if selected_notification is not None:
        if selected_notification.batch_id:
            selected_attachments = MessageAttachment.objects.filter(batch_id=selected_notification.batch_id)
        if selected_notification.thread_id:
            selected_thread = NotificationMessage.objects.select_related("actor", "recipient").filter(
                Q(recipient=request.user) | Q(actor=request.user),
                thread_id=selected_notification.thread_id,
                channel=NotificationMessage.CHANNEL_IN_APP,
                deleted_at__isnull=True,
            ).order_by("created_at", "id")
    return {
        "page_title": "Messagerie interne",
        "message_box": box,
        "filters": filters,
        "filters_options": get_notification_filter_options(request.user),
        "stats": stats,
        "unread_count": get_user_unread_count(request.user),
        "page_obj": page_obj,
        "notifications": _director_notifications_items(request, page_obj.object_list),
        "selected_notification": selected_notification,
        "selected_attachments": selected_attachments,
        "selected_thread": selected_thread,
    }


def _director_notifications_preview_context(request):
    notifications = list(get_user_in_app_messages(request.user, limit=6))
    return {
        "unread_count": get_user_unread_count(request.user),
        "notifications": _director_notifications_items(request, notifications),
    }


def _director_account_hx_trigger(message, *, tone="success", extra=None):
    payload = {"ui:toast": {"message": message, "tone": tone}}
    if extra:
        payload.update(extra)
    return json.dumps(payload, ensure_ascii=True)


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_topbar_fragments(request):
    workspace = _build_director_workspace_context(request)
    workspace.update(build_director_dashboard_presentation(request, workspace))
    account = _director_account_profile_context(request)
    return render(request, "portal/staff/director/partials/topbar_fragments.html", {
        **workspace,
        **account,
        "preview_url": reverse("accounts_portal:director_notifications_preview"),
        "center_url": f"{reverse('accounts_portal:director_workspace')}?section=messagerie",
    })


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_account_panel(request):
    view_name = (request.GET.get("view") or request.POST.get("view") or "profile").strip().lower()
    if view_name not in {"profile", "edit", "security", "preferences"}:
        return HttpResponseBadRequest("Vue de compte inconnue.")

    profile = _director_account_profile_context(request)
    system_profile, _ = Profile.objects.get_or_create(user=request.user)
    preference, _ = UserPreference.objects.get_or_create(user=request.user)

    if request.method == "POST":
        if view_name == "edit":
            form = SystemProfileForm(request.POST, request.FILES, instance=system_profile, user=request.user)
            if form.is_valid():
                form.save()
                response = render(request, "portal/staff/director/partials/account/profile.html", _director_account_profile_context(request))
                response["HX-Trigger"] = _director_account_hx_trigger("Profil mis a jour.", extra={"account:profile-updated": True})
                return response
            response = render(request, "portal/staff/director/partials/account/edit.html", {
                "form": form,
                "drawer_id": "director-drawer",
                "profile": system_profile,
            }, status=400)
            return response
        if view_name == "security":
            form = PasswordChangeForm(request.user, request.POST)
            if form.is_valid():
                user = form.save()
                update_session_auth_hash(request, user)
                response = render(request, "portal/staff/director/partials/account/security.html", {
                    "password_form": PasswordChangeForm(request.user),
                    "email": request.user.email,
                })
                response["HX-Trigger"] = _director_account_hx_trigger("Mot de passe mis a jour.", extra={"account:profile-updated": True})
                return response
            return render(request, "portal/staff/director/partials/account/security.html", {
                "password_form": form,
                "email": request.user.email,
            }, status=400)
        if view_name == "preferences":
            form = UserPreferenceForm(request.POST, instance=preference)
            if form.is_valid():
                form.save()
                response = render(request, "portal/staff/director/partials/account/preferences.html", {
                    "form": UserPreferenceForm(instance=preference),
                })
                response["HX-Trigger"] = _director_account_hx_trigger("Preferences mises a jour.", extra={"account:profile-updated": True})
                return response
            return render(request, "portal/staff/director/partials/account/preferences.html", {
                "form": form,
            }, status=400)

    if view_name == "profile":
        return render(request, "portal/staff/director/partials/account/profile.html", profile)
    if view_name == "edit":
        form = SystemProfileForm(instance=system_profile, user=request.user)
        return render(request, "portal/staff/director/partials/account/edit.html", {
            "form": form,
            "drawer_id": "director-drawer",
            "profile": system_profile,
        })
    if view_name == "security":
        return render(request, "portal/staff/director/partials/account/security.html", {
            "password_form": PasswordChangeForm(request.user),
            "email": request.user.email,
        })
    return render(request, "portal/staff/director/partials/account/preferences.html", {
        "form": UserPreferenceForm(instance=preference),
    })


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_notifications_preview(request):
    return render(request, "portal/staff/director/partials/notifications/preview.html", _director_notifications_preview_context(request))


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_notifications_workspace(request):
    context = _director_notifications_context(request)
    return render(request, "portal/staff/director/partials/notifications/workspace.html", context)


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_notification_detail(request, pk):
    notification = get_object_or_404(
        NotificationMessage.objects.select_related("actor", "recipient", "event").filter(
            Q(recipient=request.user)
            | Q(
                actor=request.user,
                event_type="internal_message",
                channel=NotificationMessage.CHANNEL_IN_APP,
            )
        ),
        pk=pk,
    )
    if (
        notification.channel == NotificationMessage.CHANNEL_IN_APP
        and notification.recipient_id == request.user.pk
        and notification.read_at is None
    ):
        NotificationBus.mark_as_read(notification)
    response = render(
        request,
        "portal/staff/director/partials/notifications/detail.html",
        {
            "notification": notification,
            "selected_attachments": (
                MessageAttachment.objects.filter(batch_id=notification.batch_id)
                if notification.batch_id else MessageAttachment.objects.none()
            ),
            "selected_thread": (
                NotificationMessage.objects.select_related("actor", "recipient").filter(
                    Q(recipient=request.user) | Q(actor=request.user),
                    thread_id=notification.thread_id,
                    channel=NotificationMessage.CHANNEL_IN_APP,
                    deleted_at__isnull=True,
                ).order_by("created_at", "id")
                if notification.thread_id else NotificationMessage.objects.none()
            ),
        },
    )
    response["HX-Trigger"] = "notification.read"
    return response


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
@require_POST
def director_mark_all_notifications_read(request):
    now = timezone.now()
    NotificationMessage.objects.filter(
        recipient=request.user,
        read_at__isnull=True,
        archived_at__isnull=True,
        deleted_at__isnull=True,
        channel=NotificationMessage.CHANNEL_IN_APP,
    ).update(read_at=now, status=NotificationMessage.STATUS_READ, updated_at=now)
    response = render(request, "portal/staff/director/partials/notifications/workspace.html", _director_notifications_context(request))
    response["HX-Trigger"] = _director_account_hx_trigger("Toutes les notifications ont ete marquees comme lues.", extra={"notificationsChanged": True})
    return response


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_internal_message_compose(request):
    branch = _resolve_director_branch(request)
    initial = {}
    parent_message = None
    reply_to = (request.GET.get("reply_to") or request.POST.get("reply_to") or "").strip()
    if reply_to.isdigit():
        source = NotificationMessage.objects.select_related("actor", "actor__profile").filter(
            pk=int(reply_to),
            recipient=request.user,
            actor__profile__branch=branch,
        ).first()
        if source and source.actor_id != request.user.pk:
            parent_message = source
            initial = {
                "audience": "individual",
                "recipients": [source.actor_id],
                "title": f"Re: {source.title}"[:255],
            }
    forward_from = (request.GET.get("forward_from") or request.POST.get("forward_from") or "").strip()
    if forward_from.isdigit() and parent_message is None:
        source = NotificationMessage.objects.select_related("actor", "recipient").filter(
            Q(recipient=request.user) | Q(actor=request.user),
            pk=int(forward_from),
            event_type="internal_message",
            channel=NotificationMessage.CHANNEL_IN_APP,
        ).first()
        if source:
            initial = {
                "audience": "individual",
                "title": f"Tr: {source.title}"[:255],
                "body": f"\n\n--- Message transféré ---\n{source.body}",
            }

    form = DirectorInternalMessageForm(
        request.POST or None,
        request.FILES or None,
        branch=branch,
        user=request.user,
        initial=initial,
    )
    if request.method == "POST" and form.is_valid():
        try:
            result = send_director_internal_message(
                user=request.user,
                branch=branch,
                recipients=form.cleaned_data["recipients"],
                title=form.cleaned_data["title"],
                body=form.cleaned_data["body"],
                priority=form.cleaned_data["priority"],
                audience=form.cleaned_data["audience"],
                class_ids=form.cleaned_data["target_classes"].values_list("id", flat=True),
                programme_ids=form.cleaned_data["target_programmes"].values_list("id", flat=True),
                role_tokens=form.cleaned_data["target_roles"],
                attachment=form.cleaned_data.get("attachment"),
                parent_message=parent_message,
            )
        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))
        else:
            original_get = request.GET
            params = request.GET.copy()
            params["section"] = "messagerie"
            params["box"] = "sent"
            request.GET = params
            try:
                context = _director_notifications_context(request)
            finally:
                request.GET = original_get
            response = render(request, "portal/staff/director/partials/notifications/workspace.html", context)
            response["HX-Retarget"] = "#director-workspace"
            response["HX-Push-Url"] = f"{reverse('accounts_portal:portal_dashboard')}?section=messagerie&box=sent"
            response["HX-Trigger"] = _director_account_hx_trigger(
                f"Message envoyé à {result['recipient_count']} destinataire(s).",
                extra={"director-modal-close": True, "notificationsChanged": True},
            )
            return response
    return render(
        request,
        "portal/staff/director/modals/internal_message_compose.html",
        {"message_form": form, "reply_to": reply_to, "forward_from": forward_from},
    )


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
@require_POST
def director_notification_action(request, pk):
    notification = get_object_or_404(
        NotificationMessage,
        pk=pk,
        recipient=request.user,
        channel=NotificationMessage.CHANNEL_IN_APP,
    )
    action = (request.POST.get("action") or "").strip().lower()
    if action == "archive":
        NotificationBus.archive(notification)
        message = "Message archivé."
    elif action == "unarchive":
        NotificationBus.unarchive(notification)
        message = "Message replacé dans la boîte de réception."
    elif action == "read":
        NotificationBus.mark_as_read(notification)
        message = "Message marqué comme lu."
    elif action == "unread":
        notification.read_at = None
        notification.status = NotificationMessage.STATUS_DELIVERED
        notification.save(update_fields=["read_at", "status", "updated_at"])
        message = "Message marqué comme non lu."
    elif action == "pin":
        notification.pinned_at = timezone.now()
        notification.save(update_fields=["pinned_at", "updated_at"])
        message = "Message épinglé."
    elif action == "unpin":
        notification.pinned_at = None
        notification.save(update_fields=["pinned_at", "updated_at"])
        message = "Message désépinglé."
    elif action == "delete":
        notification.deleted_at = timezone.now()
        notification.save(update_fields=["deleted_at", "updated_at"])
        message = "Message placé dans la corbeille."
    elif action == "restore":
        notification.deleted_at = None
        notification.save(update_fields=["deleted_at", "updated_at"])
        message = "Message restauré."
    else:
        return HttpResponseBadRequest("Action inconnue.")
    context = _director_notifications_context(request)
    response = render(request, "portal/staff/director/partials/notifications/workspace.html", context)
    response["HX-Trigger"] = _director_account_hx_trigger(
        message, extra={"notificationsChanged": True}
    )
    return response


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_workspace(request):
    context = _build_director_workspace_context(request)
    context.update(build_director_dashboard_presentation(request, context))
    if context.get("section") == "home":
        return render(request, "portal/staff/director/partials/home.html", context)
    if context.get("section") == "messagerie":
        context.update(_director_notifications_context(request))
        return render(request, "portal/staff/director/partials/notifications/workspace.html", context)
    return render(request, "portal/staff/director/partials/workspace.html", context)


_EVAL_SUBVIEW_TEMPLATES = {
    "overview": "portal/staff/director/partials/evaluations/overview.html",
    "validation": "portal/staff/director/partials/evaluations/validation.html",
}

_EXAM_SESSION_SUBVIEW_TEMPLATES = {
    "overview": "portal/staff/director/partials/evaluation_sessions/overview.html",
    "sessions": "portal/staff/director/partials/evaluation_sessions/sessions.html",
    "create": "portal/staff/director/partials/evaluation_sessions/create.html",
    "scheduled": "portal/staff/director/partials/evaluation_sessions/scheduled.html",
}

_PROGRAMME_SUBVIEW_TEMPLATES = {
    "overview": "portal/staff/director/partials/programme/overview.html",
    "classes": "portal/staff/director/partials/programme/classes.html",
    "maquettes": "portal/staff/director/partials/programme/maquettes.html",
}

_TEACHER_SUBVIEW_TEMPLATES = {
    "overview": "portal/staff/director/partials/teachers/overview.html",
    "directory": "portal/staff/director/partials/teachers/directory.html",
    "assignments": "portal/staff/director/partials/teachers/assignments.html",
    "files": "portal/staff/director/partials/teachers/files.html",
}

_DOCUMENT_SUBVIEW_TEMPLATES = {
    "overview": "portal/staff/director/partials/documents/overview.html",
    "create": "portal/staff/director/partials/documents/create.html",
    "archives": "portal/staff/director/partials/documents/archives.html",
}

_TIMETABLE_SUBVIEW_TEMPLATES = {
    "overview": "portal/staff/director/partials/timetable/overview.html",
    "builder": "portal/staff/director/partials/timetable/builder.html",
    "preview": "portal/staff/director/partials/timetable/preview.html",
}

_TRANSFER_SUBVIEW_TEMPLATES = {
    "overview": "portal/staff/director/partials/transfers/overview.html",
    "pending": "portal/staff/director/partials/transfers/pending.html",
    "history": "portal/staff/director/partials/transfers/history.html",
}

_SALARY_SUBVIEW_TEMPLATES = {
    "overview": "portal/staff/director/partials/salary/overview.html",
    "history": "portal/staff/director/partials/salary/history.html",
}


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_timetable_subcontent(request):
    raw_view = (request.GET.get("view") or "").strip().lower()
    subview = raw_view if raw_view in _TIMETABLE_SUBVIEW_TEMPLATES else "overview"
    original_get = request.GET
    params = request.GET.copy()
    params["section"] = "planification"
    params["view"] = subview
    request.GET = params
    try:
        context = _build_director_workspace_context(request)
        context["timetable_subview"] = subview
        context["director_fragment_response"] = True
    finally:
        request.GET = original_get
    response = render(request, _TIMETABLE_SUBVIEW_TEMPLATES[subview], context)
    response["HX-Push-Url"] = _director_subview_push_url(
        request, section="planification", subview=subview
    )
    return response


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_timetable_slot_drawer(request):
    branch = _resolve_director_branch(request)
    if branch is None:
        return HttpResponseBadRequest("Aucune annexe.")
    class_id = (request.GET.get("class_id") or "").strip()
    academic_class = AcademicClass.objects.select_related(
        "programme", "academic_year", "branch"
    ).filter(
        pk=class_id,
        branch=branch,
        is_active=True,
        is_archived=False,
    ).first()
    if academic_class is None:
        return HttpResponseBadRequest("Classe introuvable.")

    slot = None
    slot_id = (request.GET.get("slot_id") or "").strip()
    if slot_id:
        slot = WeeklyScheduleSlot.objects.filter(
            pk=slot_id,
            academic_class=academic_class,
            branch=branch,
            is_active=True,
        ).first()
        if slot is None:
            return HttpResponseBadRequest("Créneau introuvable.")

    initial = {}
    if slot is None:
        weekday = (request.GET.get("weekday") or "").strip()
        if weekday.isdigit() and 0 <= int(weekday) <= 5:
            initial["weekday"] = int(weekday)
        start_time = (request.GET.get("start_time") or "").strip()
        end_time = (request.GET.get("end_time") or "").strip()
        if start_time:
            initial["start_time"] = start_time
        if end_time:
            initial["end_time"] = end_time

    form = DirectorWeeklyScheduleSlotForm(
        branch=branch,
        academic_class=academic_class,
        instance=slot,
        initial=initial,
    )
    return render(
        request,
        "portal/staff/director/partials/timetable/slot_drawer.html",
        {
            "timetable_slot_form": form,
            "timetable_selected_class": academic_class,
            "timetable_editing_slot": slot,
            "timetable_week_start": _parse_director_week_start(request),
        },
    )


def _director_timetable_builder_response(
    request, *, branch, academic_class, toast, close_drawer=False
):
    week_start = _parse_director_week_start(request)
    context = build_director_timetable_context(
        branch=branch,
        subview="builder",
        selected_class_id=academic_class.pk,
        week_start=week_start,
    )
    context["toast"] = toast
    context["director_fragment_response"] = True
    response = render(request, _TIMETABLE_SUBVIEW_TEMPLATES["builder"], context)
    response["HX-Retarget"] = "#director-timetable-subcontent"
    response["HX-Reswap"] = "innerHTML"
    response["HX-Push-Url"] = (
        f"{reverse('accounts_portal:portal_dashboard')}"
        f"?section=planification&view=builder&class_id={academic_class.pk}"
        f"&week_start={week_start.isoformat()}"
    )
    if close_drawer:
        response["HX-Trigger"] = "director-drawer-close"
    return response


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_timetable_action(request):
    if request.method != "POST":
        return _deny_portal_access(request)
    branch = _resolve_director_branch(request)
    if branch is None:
        return HttpResponseBadRequest("Aucune annexe.")
    class_id = (request.POST.get("class_id") or "").strip()
    academic_class = AcademicClass.objects.select_related(
        "programme", "academic_year", "branch"
    ).filter(
        pk=class_id,
        branch=branch,
        is_active=True,
        is_archived=False,
    ).first()
    if academic_class is None:
        return HttpResponseBadRequest("Classe introuvable.")

    action = (request.POST.get("action") or "save").strip().lower()
    slot_id = (request.POST.get("slot_id") or "").strip()

    if action == "delete":
        slot = WeeklyScheduleSlot.objects.filter(
            pk=slot_id,
            academic_class=academic_class,
            branch=branch,
            is_active=True,
        ).first()
        if slot is None:
            return HttpResponseBadRequest("Créneau introuvable.")
        deactivate_weekly_schedule_slot(slot)
        return _director_timetable_builder_response(
            request,
            branch=branch,
            academic_class=academic_class,
            toast={"level": "success", "message": "Le créneau a été retiré de la grille."},
        )

    if action in {"materialize_week", "materialize_month"}:
        result = _materialize_period_from_weekly_slots(
            user=request.user,
            academic_class=academic_class,
            week_start=_parse_director_week_start(request),
            weeks_count=4 if action == "materialize_month" else 1,
        )
        return _director_timetable_builder_response(
            request,
            branch=branch,
            academic_class=academic_class,
            toast={
                "level": "success",
                "message": (
                    f"Période actualisée : {result['created']} cours créés, "
                    f"{result['skipped_existing']} déjà présents."
                ),
            },
        )

    editing_slot = None
    if slot_id:
        editing_slot = WeeklyScheduleSlot.objects.filter(
            pk=slot_id,
            academic_class=academic_class,
            branch=branch,
            is_active=True,
        ).first()
        if editing_slot is None:
            return HttpResponseBadRequest("Créneau introuvable.")

    form = DirectorWeeklyScheduleSlotForm(
        request.POST,
        branch=branch,
        academic_class=academic_class,
        instance=editing_slot,
    )
    if form.is_valid():
        values = {
            "weekday": form.cleaned_data["weekday"],
            "start_time": form.cleaned_data["start_time"],
            "end_time": form.cleaned_data["end_time"],
            "ec": form.cleaned_data["ec_id"],
            "teacher": form.cleaned_data["teacher_id"],
            "room": form.cleaned_data["room"].strip(),
            "is_active": True,
        }
        try:
            if editing_slot is None:
                create_weekly_schedule_slot(
                    user=request.user,
                    academic_class=academic_class,
                    branch=branch,
                    academic_year=academic_class.academic_year,
                    **values,
                )
                message = "Le cours a été ajouté à l'emploi du temps."
            else:
                update_weekly_schedule_slot(editing_slot, **values)
                message = "Le cours a été mis à jour dans l'emploi du temps."
        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))
        else:
            return _director_timetable_builder_response(
                request,
                branch=branch,
                academic_class=academic_class,
                toast={"level": "success", "message": message},
                close_drawer=True,
            )

    return render(
        request,
        "portal/staff/director/partials/timetable/slot_drawer.html",
        {
            "timetable_slot_form": form,
            "timetable_selected_class": academic_class,
            "timetable_editing_slot": editing_slot,
            "timetable_week_start": _parse_director_week_start(request),
        },
    )


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_evaluations_subcontent(request):
    """Charge un fragment Resultats et notes, jamais un ecran de planification."""
    raw_view = (request.GET.get("view") or "").strip().lower()
    subview = raw_view if raw_view in _EVAL_SUBVIEW_TEMPLATES else "overview"
    original_get = request.GET
    params = request.GET.copy()
    params["section"] = "evaluations"
    request.GET = params
    try:
        context = _build_director_workspace_context(request)
        context["eval_subview"] = subview
        context["director_fragment_response"] = True
    finally:
        request.GET = original_get
    response = render(request, _EVAL_SUBVIEW_TEMPLATES[subview], context)
    response["HX-Push-Url"] = _director_subview_push_url(
        request, section="evaluations", subview=subview
    )
    return response


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_exam_sessions_subcontent(request):
    """Charge un fragment de planification dans Sessions d'evaluations."""
    raw_view = (request.GET.get("view") or "").strip().lower()
    subview = (
        raw_view if raw_view in _EXAM_SESSION_SUBVIEW_TEMPLATES else "overview"
    )
    original_get = request.GET
    params = request.GET.copy()
    params["section"] = "evaluations_calendar"
    params["view"] = subview
    request.GET = params
    try:
        context = _build_director_workspace_context(request)
        context["session_subview"] = subview
        context["director_fragment_response"] = True
    finally:
        request.GET = original_get
    response = render(request, _EXAM_SESSION_SUBVIEW_TEMPLATES[subview], context)
    response["HX-Push-Url"] = _director_subview_push_url(
        request, section="evaluations_calendar", subview=subview
    )
    return response


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_programme_subcontent(request):
    """Charge une sous-vue du programme sans remplacer le dashboard complet."""
    raw_view = (request.GET.get("view") or "").strip().lower()
    subview = raw_view if raw_view in _PROGRAMME_SUBVIEW_TEMPLATES else "overview"
    original_get = request.GET
    params = request.GET.copy()
    params["section"] = "programme"
    params["view"] = subview
    request.GET = params
    try:
        context = _build_director_workspace_context(request)
        context["programme_subview"] = subview
        context["director_fragment_response"] = True
    finally:
        request.GET = original_get
    response = render(request, _PROGRAMME_SUBVIEW_TEMPLATES[subview], context)
    response["HX-Push-Url"] = _director_subview_push_url(
        request, section="programme", subview=subview
    )
    return response


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_teachers_subcontent(request):
    raw_view = (request.GET.get("view") or "").strip().lower()
    subview = raw_view if raw_view in _TEACHER_SUBVIEW_TEMPLATES else "overview"
    original_get = request.GET
    params = request.GET.copy()
    params["section"] = "enseignants"
    params["view"] = subview
    request.GET = params
    try:
        context = _build_director_workspace_context(request)
        context["teacher_subview"] = subview
        context["director_fragment_response"] = True
    finally:
        request.GET = original_get
    response = render(request, _TEACHER_SUBVIEW_TEMPLATES[subview], context)
    response["HX-Push-Url"] = _director_subview_push_url(
        request, section="enseignants", subview=subview
    )
    return response


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_transfers_subcontent(request):
    raw_view = (request.GET.get("view") or "").strip().lower()
    subview = raw_view if raw_view in _TRANSFER_SUBVIEW_TEMPLATES else "overview"
    original_get = request.GET
    params = request.GET.copy()
    params["section"] = "transferts"
    params["view"] = subview
    request.GET = params
    try:
        context = _build_director_workspace_context(request)
        context["transfer_subview"] = subview
        context["director_fragment_response"] = True
    finally:
        request.GET = original_get
    response = render(request, _TRANSFER_SUBVIEW_TEMPLATES[subview], context)
    response["HX-Push-Url"] = _director_subview_push_url(
        request, section="transferts", subview=subview
    )
    return response


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_salary_subcontent(request):
    raw_view = (request.GET.get("view") or "").strip().lower()
    subview = raw_view if raw_view in _SALARY_SUBVIEW_TEMPLATES else "overview"
    original_get = request.GET
    params = request.GET.copy()
    params["section"] = "salaire"
    params["view"] = subview
    request.GET = params
    try:
        context = _build_director_workspace_context(request)
        context["salary_subview"] = subview
        context["director_fragment_response"] = True
    finally:
        request.GET = original_get
    response = render(request, _SALARY_SUBVIEW_TEMPLATES[subview], context)
    response["HX-Push-Url"] = _director_subview_push_url(
        request, section="salaire", subview=subview
    )
    return response


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_documents_subcontent(request):
    raw_view = (request.GET.get("view") or "").strip().lower()
    subview = raw_view if raw_view in _DOCUMENT_SUBVIEW_TEMPLATES else "overview"
    original_get = request.GET
    params = request.GET.copy()
    params["section"] = "correspondances"
    params["view"] = subview
    request.GET = params
    try:
        context = _build_director_workspace_context(request)
        context["document_subview"] = subview
        context["director_fragment_response"] = True
    finally:
        request.GET = original_get
    response = render(request, _DOCUMENT_SUBVIEW_TEMPLATES[subview], context)
    response["HX-Push-Url"] = _director_subview_push_url(
        request, section="correspondances", subview=subview
    )
    return response


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_teacher_ec_options(request):
    branch = _resolve_director_branch(request)
    class_id = (request.GET.get("class_id") or "").strip()
    mode = (request.GET.get("mode") or "assignment").strip().lower()
    if mode == "create":
        form = DirectorTeacherCreateForm(branch=branch, initial={"class_id": class_id})
        field = form["ec_id"]
        field_id = "director-teacher-create-ec-field"
    else:
        form = DirectorTeacherAssignmentForm(branch=branch, initial={"class_id": class_id})
        field = form["ec_id"]
        field_id = "director-teacher-assignment-ec-field"
    return render(
        request,
        "portal/staff/director/partials/teachers/_ec_field.html",
        {"field": field, "field_id": field_id},
    )


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_programme_class_modal(request):
    branch = _resolve_director_branch(request)
    if branch is None:
        return HttpResponseBadRequest("Aucune annexe.")
    raw_class_id = (request.GET.get("class_id") or "").strip()
    academic_class = None
    if raw_class_id:
        if not raw_class_id.isdigit():
            return HttpResponseBadRequest("Classe invalide.")
        academic_class = AcademicClass.objects.filter(
            pk=int(raw_class_id), branch=branch, is_archived=False
        ).first()
        if academic_class is None:
            return HttpResponseBadRequest("Classe introuvable.")
    form = DirectorProgrammeClassForm(
        branch=branch, instance=academic_class
    )
    return render(
        request,
        "portal/staff/director/partials/programme/class_modal.html",
        {"programme_class_form": form, "programme_class": academic_class},
    )


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_evaluation_ec_options(request):
    branch = _resolve_director_branch(request)
    class_id = (request.GET.get("class_id") or "").strip()
    form = DirectorEvaluationForm(branch=branch, selected_class_id=class_id)
    return render(
        request,
        "portal/staff/director/partials/evaluation_sessions/_ec_field.html",
        {"evaluation_form": form},
    )


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_drawer(request):
    panel = (request.GET.get("panel") or "").strip().lower()
    section_map = {
        "operation": "operations",
        "result": "results",
        "student": "students",
        "programme": "programme",
        "planification": "planification",
        "evaluations": "evaluations",
    }
    template_map = {
        "operation": "portal/staff/director/partials/drawers/operation_drawer.html",
        "result": "portal/staff/director/partials/drawers/result_drawer.html",
        "student": "portal/staff/director/partials/drawers/student_drawer.html",
        "programme": "portal/staff/director/partials/drawers/programme_drawer.html",
        "planification": "portal/staff/director/partials/drawers/planification_drawer.html",
        "evaluations": "portal/staff/director/partials/drawers/evaluations_drawer.html",
    }
    section = section_map.get(panel)
    template_name = template_map.get(panel)
    if not section or not template_name:
        return HttpResponseBadRequest("Panneau introuvable.")

    original_get = request.GET
    params = request.GET.copy()
    params["section"] = section
    request.GET = params
    try:
        context = _build_director_workspace_context(request)
    finally:
        request.GET = original_get

    if panel == "operation" and not context.get("selected_operation_class"):
        return HttpResponseBadRequest("Classe introuvable.")
    if panel == "result" and not context.get("selected_semester_row"):
        return HttpResponseBadRequest("Semestre introuvable.")
    if panel == "student" and not context.get("selected_student_entry"):
        return HttpResponseBadRequest("Etudiant introuvable.")
    if panel in {"programme", "planification", "evaluations"} and not context.get("selected_class"):
        return HttpResponseBadRequest("Classe introuvable.")

    return render(request, template_name, context)


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_programme_action(request):
    if request.method != "POST":
        return _deny_portal_access(request)
    branch = _resolve_director_branch(request)
    if not branch:
        return HttpResponseBadRequest("Aucune annexe.")
    action = (request.POST.get("action") or "").strip()
    class_id = (request.POST.get("class_id") or "").strip()
    toast = None

    def _programme_form_class():
        if not class_id or not class_id.isdigit():
            return None
        return AcademicClass.objects.filter(
            pk=int(class_id), branch=branch, is_active=True, is_archived=False
        ).first()

    def _first_form_error(bound_form, fallback):
        for errors in bound_form.errors.values():
            if errors:
                return errors[0]
        return fallback

    if action == "save_class":
        academic_class = None
        if class_id:
            if not class_id.isdigit():
                return HttpResponseBadRequest("Classe invalide.")
            academic_class = AcademicClass.objects.filter(
                pk=int(class_id), branch=branch, is_archived=False
            ).first()
            if academic_class is None:
                return HttpResponseBadRequest("Classe introuvable.")
        form = DirectorProgrammeClassForm(
            request.POST, branch=branch, instance=academic_class
        )
        if form.is_valid():
            try:
                saved_class = save_academic_class(
                    branch=branch,
                    class_id=getattr(academic_class, "pk", None),
                    programme_id=form.cleaned_data["programme"].pk,
                    academic_year_id=form.cleaned_data["academic_year"].pk,
                    level=form.cleaned_data["level"],
                    threshold=form.cleaned_data.get("validation_threshold") or "",
                    actor=request.user,
                )
            except ValidationError as exc:
                form.add_error(None, " ".join(exc.messages))
            else:
                original_get = request.GET
                params = request.GET.copy()
                params["section"] = "programme"
                params["view"] = "classes"
                params["class_id"] = str(saved_class.pk)
                request.GET = params
                try:
                    context = _build_director_workspace_context(
                        request,
                        toast={
                            "level": "success",
                            "message": "Classe enregistrée avec succès.",
                        },
                    )
                    context["director_fragment_response"] = True
                finally:
                    request.GET = original_get
                response = render(
                    request, _PROGRAMME_SUBVIEW_TEMPLATES["classes"], context
                )
                response["HX-Retarget"] = "#director-programme-subcontent"
                response["HX-Push-Url"] = (
                    f"{reverse('accounts_portal:portal_dashboard')}"
                    f"?section=programme&view=classes&class_id={saved_class.pk}"
                )
                response["HX-Trigger"] = "director-modal-close"
                return response
        return render(
            request,
            "portal/staff/director/partials/programme/class_modal.html",
            {"programme_class_form": form, "programme_class": academic_class},
        )

    bound_form = None
    form_kind = ""
    try:
        if action == "save_semester":
            academic_class = _programme_form_class()
            if academic_class is None:
                raise ValidationError("Classe introuvable ou inactive.")
            bound_form = DirectorSemesterForm(
                request.POST, branch=branch, academic_class=academic_class
            )
            form_kind = "semester"
            if not bound_form.is_valid():
                raise ValidationError(
                    _first_form_error(bound_form, "Corrigez les champs du formulaire semestre.")
                )
            sem = save_semester(branch=branch, class_id=class_id, number=bound_form.cleaned_data["number"])
            class_id = str(sem.academic_class_id)
            toast = {"level": "success", "message": f"Semestre {sem.number} créé avec succès."}
        elif action == "save_ue":
            academic_class = _programme_form_class()
            legacy_semester_id = (request.POST.get("semester_id") or "").strip()
            if academic_class is None and legacy_semester_id:
                semester = Semester.objects.filter(
                    pk=legacy_semester_id, academic_class__branch=branch
                ).first()
                if semester is None:
                    raise ValidationError("Semestre invalide pour cette annexe.")
                class_id = str(semester.academic_class_id)
                academic_class = semester.academic_class
            if academic_class is None:
                raise ValidationError("Classe introuvable ou inactive.")
            bound_form = DirectorUEForm(
                request.POST, branch=branch, academic_class=academic_class
            )
            form_kind = "ue"
            if not bound_form.is_valid():
                raise ValidationError(
                    _first_form_error(bound_form, "Corrigez les champs du formulaire UE.")
                )
            ue = save_ue(
                branch=branch,
                actor=request.user,
                ue_id=(request.POST.get("ue_id") or "").strip() or None,
                semester_id=bound_form.cleaned_data["semester"].pk,
                code=bound_form.cleaned_data["code"],
                title=bound_form.cleaned_data["title"],
            )
            class_id = str(ue.semester.academic_class_id)
            toast = {"level": "success", "message": "Unité d'enseignement enregistrée."}
        elif action == "save_ec":
            academic_class = _programme_form_class()
            bound_form = DirectorECForm(
                request.POST, branch=branch, academic_class=academic_class
            )
            form_kind = "ec"
            if not bound_form.is_valid():
                raise ValidationError(
                    _first_form_error(bound_form, "Corrigez les champs du formulaire EC.")
                )
            ec = save_ec(
                branch=branch,
                actor=request.user,
                ec_id=(request.POST.get("ec_id") or "").strip() or None,
                ue_id=bound_form.cleaned_data["ue"].pk,
                title=bound_form.cleaned_data["title"],
                coefficient=bound_form.cleaned_data["coefficient"],
                credit_required=bound_form.cleaned_data["credit_required"],
            )
            class_id = str(ec.ue.semester.academic_class_id)
            toast = {"level": "success", "message": "Élément constitutif enregistré."}
        elif action == "delete_ec":
            archived_ec = delete_ec(
                branch=branch, actor=request.user, ec_id=request.POST.get("ec_id")
            )
            class_id = str(archived_ec.ue.semester.academic_class_id)
            toast = {"level": "success", "message": "EC archivé."}
        else:
            toast = {"level": "error", "message": "Action inconnue."}
    except ValidationError as exc:
        toast = {"level": "error", "message": " ".join(exc.messages)}

    reload_drawer = request.POST.get("_reload_drawer") == "1"
    params = request.GET.copy()
    params["section"] = "programme"
    if class_id:
        params["class_id"] = class_id
    request.GET = params
    context = _build_director_workspace_context(request, toast=toast)
    if form_kind == "semester" and bound_form is not None:
        context["programme_semester_form"] = bound_form
    elif form_kind == "ue" and bound_form is not None:
        context["programme_ue_form"] = bound_form
    elif form_kind == "ec" and bound_form is not None:
        context["programme_ec_form"] = bound_form
    context["programme_form_kind"] = form_kind
    if reload_drawer and class_id:
        response = render(request, "portal/staff/director/partials/drawers/programme_drawer.html", context)
        if toast and toast["level"] == "success":
            response["HX-Trigger"] = "directorProgrammeChanged"
        return response
    return render(request, "portal/staff/director/partials/workspace.html", context)


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_correspondance_create(request):
    branch = _resolve_director_branch(request)
    if not branch:
        return HttpResponseBadRequest("Aucune annexe.")
    document_id = (request.GET.get("document_id") or request.POST.get("document_id") or "").strip()
    document = None
    if document_id:
        if not document_id.isdigit():
            return HttpResponseBadRequest("Document invalide.")
        document = AdministrativeDocument.objects.filter(
            pk=int(document_id),
            branch=branch,
            status=AdministrativeDocument.STATUS_DRAFT,
        ).first()
        if document is None:
            return HttpResponseBadRequest("Brouillon introuvable.")

    if request.method == "GET":
        form = DirectorAdministrativeDocumentForm(instance=document)
        return _render_director_subview(
            request,
            section="correspondances",
            subview="create",
            template_name=_DOCUMENT_SUBVIEW_TEMPLATES["create"],
            extra={"administrative_document_form": form, "administrative_document_selected": document},
        )
    if request.method != "POST":
        return _deny_portal_access(request)

    form = DirectorAdministrativeDocumentForm(request.POST, instance=document)
    if not form.is_valid():
        return _render_director_subview(
            request,
            section="correspondances",
            subview="create",
            template_name=_DOCUMENT_SUBVIEW_TEMPLATES["create"],
            toast={"level": "error", "message": "Corrigez les champs signalés."},
            extra={"administrative_document_form": form, "administrative_document_selected": document},
        )

    action = (request.POST.get("action") or "draft").strip().lower()
    status = (
        AdministrativeDocument.STATUS_PUBLISHED
        if action == "publish"
        else AdministrativeDocument.STATUS_DRAFT
    )
    values = form.cleaned_data
    if document is None:
        document = AdministrativeDocument(branch=branch, created_by=request.user)
    document.doc_type = values["doc_type"]
    document.title = values["title"]
    document.body = values["body"]
    document.reference = values["reference"]
    document.recipients = values["recipients"]
    document.status = status
    document.save()
    message = "Document publie avec succes." if status == AdministrativeDocument.STATUS_PUBLISHED else "Brouillon enregistre."
    response = _render_director_subview(
        request,
        section="correspondances",
        subview="archives",
        template_name=_DOCUMENT_SUBVIEW_TEMPLATES["archives"],
        toast={"level": "success", "message": message},
    )
    response["HX-Retarget"] = "#director-document-subcontent"
    return response


def _build_workspace_response(request, section_override=None, toast=None):
    if section_override:
        params = request.GET.copy()
        params["section"] = section_override
        request.GET = params
    context = _build_director_workspace_context(request, toast=toast)
    return render(request, "portal/staff/director/partials/workspace.html", context)


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_correspondance_publish(request, doc_id):
    if request.method != "POST":
        return _deny_portal_access(request)
    branch = _resolve_director_branch(request)
    doc = AdministrativeDocument.objects.filter(id=doc_id, branch=branch).first()
    if not doc:
        return HttpResponseBadRequest("Document introuvable.")
    doc.status = AdministrativeDocument.STATUS_PUBLISHED
    doc.save(update_fields=["status", "updated_at"])
    response = _render_director_subview(
        request,
        section="correspondances",
        subview="archives",
        template_name=_DOCUMENT_SUBVIEW_TEMPLATES["archives"],
        toast={"level": "success", "message": "Document publie."},
    )
    response["HX-Retarget"] = "#director-document-subcontent"
    return response


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_correspondance_pdf(request, doc_id):
    branch = _resolve_director_branch(request)
    doc = AdministrativeDocument.objects.filter(id=doc_id, branch=branch).first()
    if not doc:
        return HttpResponseBadRequest("Document introuvable.")
    html_content = render(request, "portal/admin/correspondances/pdf.html", {
        "doc": doc,
        "branch": branch,
        "today": timezone.localdate(),
    })
    try:
        from weasyprint import HTML as WeasyprintHTML
        pdf_bytes = WeasyprintHTML(string=html_content.content, base_url=request.build_absolute_uri("/")).write_pdf()
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        safe_title = doc.title[:40].replace(" ", "_")
        response["Content-Disposition"] = f'inline; filename="{safe_title}.pdf"'
        return response
    except Exception:
        return html_content


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_results_action(request):
    if request.method != "POST":
        return _deny_portal_access(request)
    branch = _resolve_director_branch(request)
    action = (request.POST.get("action") or "").strip()

    if action == "publish":
        return _director_request_publish_otp(request, branch=branch)

    toast = {"level": "error", "message": "Action impossible."}
    rejected_semester_ids = {
        int(semester_id)
        for semester_id in (request.session.get("director_rejected_semester_ids") or [])
        if str(semester_id).isdigit()
    }
    try:
        semester = Semester.objects.select_related("academic_class", "academic_class__branch", "academic_class__academic_year").get(pk=request.POST.get("semester_id"))
        if branch is not None and semester.academic_class.branch_id != branch.id:
            raise ValidationError("Action hors annexe refusee.")
        enrollments = list(AcademicEnrollment.objects.filter(academic_class=semester.academic_class, academic_year=semester.academic_class.academic_year, is_active=True))
        previous_status = semester.status
        if action == "validate":
            if not can_publish_semester(semester, enrollments):
                raise ValidationError("Toutes les notes doivent etre renseignees avant validation.")
            semester.status = Semester.STATUS_FINALIZED
            semester.save(update_fields=["status"])
            rejected_semester_ids.discard(semester.id)
            toast = {"level": "success", "message": "Resultats valides. Publication possible."}
            log_action(
                request.user,
                "semester.validated",
                semester,
                old_values={"status": previous_status},
                new_values={"status": semester.status},
                branch=semester.academic_class.branch,
                academic_year=semester.academic_class.academic_year,
                request=request,
            )
        elif action == "reject":
            if semester.status == Semester.STATUS_PUBLISHED:
                raise ValidationError("Un semestre publie ne peut pas etre rejete ici.")
            semester.status = Semester.STATUS_NORMAL_ENTRY
            semester.save(update_fields=["status"])
            rejected_semester_ids.add(semester.id)
            toast = {"level": "success", "message": "Resultats renvoyes en correction."}
            log_action(
                request.user,
                "semester.rejected",
                semester,
                old_values={"status": previous_status},
                new_values={"status": semester.status},
                branch=semester.academic_class.branch,
                academic_year=semester.academic_class.academic_year,
                request=request,
            )
        else:
            raise ValidationError("Action inconnue.")
    except (Semester.DoesNotExist, ValidationError) as exc:
        message = " ".join(getattr(exc, "messages", [])) if hasattr(exc, "messages") else str(exc)
        toast = {"level": "error", "message": message or "Action impossible."}
    request.session["director_rejected_semester_ids"] = sorted(rejected_semester_ids)
    response = _render_director_subview(
        request,
        section="evaluations",
        subview="validation",
        template_name=_EVAL_SUBVIEW_TEMPLATES["validation"],
        toast=toast,
    )
    response["HX-Trigger"] = "directorResultsChanged"
    return response


def _director_request_publish_otp(request, *, branch):
    """Publication = action irreversible : declenche une demande OTP au DG/DGA
    de l'annexe au lieu de changer le statut directement (cf.
    CAHIER_DES_CHARGES_DIRECTEUR_ETUDES.md, 2.1)."""
    try:
        semester = Semester.objects.select_related(
            "academic_class", "academic_class__branch", "academic_class__academic_year"
        ).get(pk=request.POST.get("semester_id"))
        if branch is not None and semester.academic_class.branch_id != branch.id:
            raise ValidationError("Action hors annexe refusee.")
        if semester.status != Semester.STATUS_FINALIZED:
            raise ValidationError("Le semestre doit etre valide avant publication.")
        otp_request = request_sensitive_action(
            branch=semester.academic_class.branch,
            action_type=SensitiveActionRequest.ACTION_SEMESTER_PUBLISH,
            target_model="Semester",
            target_id=semester.pk,
            previous_state={"status": semester.status},
            requested_state={"status": Semester.STATUS_PUBLISHED},
            requested_by=request.user,
        )
    except (Semester.DoesNotExist, ValidationError, SensitiveActionError) as exc:
        message = " ".join(getattr(exc, "messages", [])) if hasattr(exc, "messages") else str(exc)
        return render(
            request,
            "portal/staff/director/partials/results_otp_modal.html",
            {"otp_error": message or "Publication impossible."},
        )

    return render(
        request,
        "portal/staff/director/partials/results_otp_modal.html",
        {
            "otp_request_id": otp_request.pk,
            "otp_validity_minutes": SensitiveActionRequest.OTP_VALIDITY_MINUTES,
            "class_label": semester.academic_class.display_name,
            "semester_number": semester.number,
        },
    )


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_results_confirm_otp(request):
    if request.method != "POST":
        return _deny_portal_access(request)
    otp_request_id = request.POST.get("otp_request_id")
    otp_code = (request.POST.get("otp_code") or "").strip()
    branch = _resolve_director_branch(request)

    def _apply(otp_request):
        semester = Semester.objects.select_related(
            "academic_class", "academic_class__branch", "academic_class__academic_year"
        ).get(pk=otp_request.target_id)
        previous_status = semester.status
        semester.status = Semester.STATUS_PUBLISHED
        semester.save(update_fields=["status"])

        rejected_semester_ids = {
            int(semester_id)
            for semester_id in (request.session.get("director_rejected_semester_ids") or [])
            if str(semester_id).isdigit()
        }
        rejected_semester_ids.discard(semester.id)
        request.session["director_rejected_semester_ids"] = sorted(rejected_semester_ids)

        log_action(
            otp_request.requested_by,
            "semester.published",
            semester,
            old_values={"status": previous_status},
            new_values={"status": semester.status},
            branch=semester.academic_class.branch,
            academic_year=semester.academic_class.academic_year,
            reason=otp_request.reason,
            request=request,
        )
        return {"status": semester.status}

    toast = None
    try:
        scoped_request = SensitiveActionRequest.objects.filter(pk=otp_request_id).first()
        if scoped_request is None:
            raise SensitiveActionRequest.DoesNotExist
        if branch is not None and scoped_request.branch_id != branch.id:
            raise SensitiveActionError("Action hors annexe refusee.")
        confirm_sensitive_action(
            request_id=otp_request_id,
            code=otp_code,
            approver=request.user,
            apply_callback=_apply,
            skip_financial_audit=True,
        )
        toast = {"level": "success", "message": "Resultats publies."}
    except (SensitiveActionError, SensitiveActionRequest.DoesNotExist) as exc:
        message = str(exc) if isinstance(exc, SensitiveActionError) else "Demande introuvable."
        toast = {"level": "error", "message": message}

    if toast["level"] != "success":
        semester = None
        if scoped_request is not None and str(scoped_request.target_id).isdigit():
            semester = Semester.objects.select_related("academic_class").filter(
                pk=scoped_request.target_id
            ).first()
        return render(
            request,
            "portal/staff/director/partials/results_otp_modal.html",
            {
                "otp_error": toast["message"],
                "otp_request_id": getattr(scoped_request, "pk", None),
                "otp_validity_minutes": SensitiveActionRequest.OTP_VALIDITY_MINUTES,
                "class_label": getattr(getattr(semester, "academic_class", None), "display_name", ""),
                "semester_number": getattr(semester, "number", ""),
            },
        )

    response = _render_director_subview(
        request,
        section="evaluations",
        subview="validation",
        template_name=_EVAL_SUBVIEW_TEMPLATES["validation"],
        toast=toast,
    )
    response["HX-Retarget"] = "#director-results-subcontent"
    response["HX-Trigger"] = "director-modal-close, directorResultsChanged"
    return response


@_position_required(BULLETIN_MANAGEMENT_POSITIONS)
def director_bulletin_action(request):
    if request.method != "POST":
        return _deny_portal_access(request)
    branch = _resolve_director_branch(request)
    action = (request.POST.get("action") or "").strip()
    toast = {"level": "error", "message": "Action bulletin impossible."}
    try:
        if action == "generate_semester_class":
            semester = Semester.objects.select_related("academic_class", "academic_class__branch").get(pk=request.POST.get("semester_id"))
            if branch is not None and semester.academic_class.branch_id != branch.id:
                raise ValidationError("Action hors annexe refusee.")
            if not can_manage_bulletins(request.user, semester.academic_class):
                raise ValidationError("Seul le Directeur des etudes peut delivrer les bulletins.")
            bulletins = generate_semester_bulletins_for_class(
                academic_class=semester.academic_class,
                semester=semester,
                actor=request.user,
                publish=True,
            )
            toast = {"level": "success", "message": f"{len(bulletins)} bulletin(s) semestriel(s) generes."}
        elif action == "generate_annual_class":
            academic_class = AcademicClass.objects.select_related("branch", "academic_year").get(pk=request.POST.get("class_id"))
            if branch is not None and academic_class.branch_id != branch.id:
                raise ValidationError("Action hors annexe refusee.")
            if not can_manage_bulletins(request.user, academic_class):
                raise ValidationError("Seul le Directeur des etudes peut delivrer les bulletins.")
            bulletins = generate_annual_bulletins_for_class(
                academic_class=academic_class,
                actor=request.user,
                publish=True,
            )
            toast = {"level": "success", "message": f"{len(bulletins)} bulletin(s) annuel(s) generes."}
        else:
            raise ValidationError("Action bulletin inconnue.")
    except (Semester.DoesNotExist, AcademicClass.DoesNotExist):
        toast = {"level": "error", "message": "Classe ou semestre introuvable."}
    except ValidationError as exc:
        toast = {"level": "error", "message": " ".join(exc.messages)}
    response = _render_director_subview(
        request,
        section="evaluations",
        subview="validation",
        template_name=_EVAL_SUBVIEW_TEMPLATES["validation"],
        toast=toast,
    )
    response["HX-Trigger"] = "directorResultsChanged"
    return response


@_position_required(BULLETIN_MANAGEMENT_POSITIONS)
def director_export_report_xlsx(request):
    branch = _resolve_director_branch(request)
    wb = build_academic_report_xlsx(branch=branch)
    branch_slug = branch.slug if branch else "toutes_annexes"
    filename = f"rapport_pedagogique_{branch_slug}.xlsx"
    return xlsx_response(wb, filename)


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_teacher_create(request):
    branch = _resolve_director_branch(request)
    if branch is None:
        return HttpResponseBadRequest("Aucune annexe.")

    if request.method == "GET":
        return render(
            request,
            "portal/staff/director/modals/teacher_create_modal.html",
            {"teacher_form": DirectorTeacherCreateForm(branch=branch)},
        )

    if request.method != "POST":
        return _deny_portal_access(request)

    form = DirectorTeacherCreateForm(request.POST, branch=branch)
    if not form.is_valid():
        return render(
            request,
            "portal/staff/director/modals/teacher_create_modal.html",
            {"teacher_form": form, "toast": {"level": "error", "message": "Corrigez les champs signalés."}},
        )
    try:
        values = form.cleaned_data
        create_teacher_with_account(
            {
                "first_name": values["first_name"],
                "last_name": values["last_name"],
                "email": values["email"],
                "phone": values["phone"],
                "teacher_hourly_rate": values["teacher_hourly_rate"],
                "specialty": values["specialty"],
                "class_id": str(values["class_id"].pk) if values["class_id"] else "",
                "ec_id": str(values["ec_id"].pk) if values["ec_id"] else "",
                "room_label": values["room_label"],
                "planned_hours": str(values["planned_hours"] or ""),
            },
            request.user,
        )
    except ValidationError as exc:
        form.add_error(None, " ".join(exc.messages) or "Creation impossible.")
        return render(
            request,
            "portal/staff/director/modals/teacher_create_modal.html",
            {"teacher_form": form, "toast": {"level": "error", "message": "Creation impossible."}},
        )

    response = _render_director_subview(
        request,
        section="enseignants",
        subview="directory",
        template_name=_TEACHER_SUBVIEW_TEMPLATES["directory"],
        toast={"level": "success", "message": "Enseignant cree, affecte et acces generes."},
    )
    response["HX-Retarget"] = "#director-teacher-subcontent"
    response["HX-Trigger"] = "director-modal-close"
    return response


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def _legacy_director_teacher_assign(request):
    """Modale d'affectation enseignant -> classe/EC/salle (GET: modal, POST: sauvegarde)."""
    branch = _resolve_director_branch(request)
    User = get_user_model()

    teacher_id_raw = (request.GET.get("teacher_id") or request.POST.get("teacher_id") or "").strip()
    teacher_id = int(teacher_id_raw) if teacher_id_raw.isdigit() else None
    teacher = None
    if teacher_id:
        teacher = User.objects.select_related("profile", "profile__branch").filter(
            id=teacher_id, is_active=True, profile__position="teacher"
        )
        if branch is not None:
            teacher = teacher.filter(profile__branch=branch)
        teacher = teacher.first()

    if request.method == "GET":
        classes_qs = AcademicClass.objects.select_related("programme", "academic_year").filter(is_active=True)
        if branch:
            classes_qs = classes_qs.filter(branch=branch)
        ecs_qs = EC.objects.select_related(
            "ue", "ue__semester", "ue__semester__academic_class"
        )
        if branch:
            ecs_qs = ecs_qs.filter(ue__semester__academic_class__branch=branch)
        existing = []
        if teacher:
            existing_qs = DirectorTeacherAssignment.objects.select_related("academic_class", "ec").filter(
                teacher=teacher, is_active=True
            )
            if branch is not None:
                existing_qs = existing_qs.filter(branch=branch)
            existing = list(existing_qs)
        selected_class_id = ""
        selected_ec_id = ""
        selected_room_label = ""
        selected_planned_hours = ""
        if existing:
            selected_class_id = str(existing[0].academic_class_id or "")
            selected_ec_id = str(existing[0].ec_id or "")
            selected_room_label = existing[0].room_label or ""
            selected_planned_hours = str(existing[0].planned_hours or "")
        return render(request, "portal/staff/director/modals/teacher_assign_modal.html", {
            "assign_teacher": teacher,
            "assign_teacher_name": teacher.get_full_name() or teacher.username if teacher else "",
            "assign_classes": list(classes_qs.order_by("level", "programme__title")[:80]),
            "assign_ecs": list(ecs_qs.order_by("title")[:120]),
            "assign_existing": existing,
            "assign_selected_class_id": selected_class_id,
            "assign_selected_ec_id": selected_ec_id,
            "assign_selected_room_label": selected_room_label,
            "assign_selected_planned_hours": selected_planned_hours,
        })

    # POST
    action = (request.POST.get("action") or "add").strip()
    toast = {"level": "error", "message": "Action impossible."}
    try:
        if teacher is None:
            raise ValidationError("Enseignant introuvable.")
        if branch is not None and getattr(getattr(teacher, "profile", None), "branch_id", None) != branch.id:
            raise ValidationError("Affectation hors perimetre refusee.")

        assignment_id_raw = (request.POST.get("assignment_id") or "").strip()
        assignment_id = int(assignment_id_raw) if assignment_id_raw.isdigit() else None
        assignment = DirectorTeacherAssignment.objects.select_related(
            "branch",
            "teacher",
            "academic_class",
            "semester",
            "ue",
            "ec",
        ).filter(id=assignment_id, teacher=teacher).first() if assignment_id else None
        if branch is not None and assignment is not None and assignment.branch_id != branch.id:
            raise ValidationError("Affectation hors perimetre refusee.")

        if action in {"remove", "archive"}:
            if assignment is None:
                raise ValidationError("Affectation introuvable.")
            archive_teacher_assignment(actor=request.user, assignment=assignment, branch=branch or assignment.branch)
            toast = {"level": "success", "message": "Affectation retiree."}
        elif action == "suspend":
            if assignment is None:
                raise ValidationError("Affectation introuvable.")
            suspend_teacher_assignment(actor=request.user, assignment=assignment, branch=branch or assignment.branch)
            toast = {"level": "success", "message": "Affectation suspendue."}
        elif action == "activate":
            if assignment is None:
                raise ValidationError("Affectation introuvable.")
            activate_teacher_assignment(actor=request.user, assignment=assignment, branch=branch or assignment.branch)
            toast = {"level": "success", "message": "Affectation activee."}
        else:
            class_id_raw = (request.POST.get("class_id") or "").strip()
            class_id = int(class_id_raw) if class_id_raw.isdigit() else None
            semester_id_raw = (request.POST.get("semester_id") or "").strip()
            semester_id = int(semester_id_raw) if semester_id_raw.isdigit() else None
            ue_id_raw = (request.POST.get("ue_id") or "").strip()
            ue_id = int(ue_id_raw) if ue_id_raw.isdigit() else None
            ec_id_raw = (request.POST.get("ec_id") or "").strip()
            ec_id = int(ec_id_raw) if ec_id_raw.isdigit() else None
            room_label = (request.POST.get("room_label") or "").strip()
            planned_hours_raw = (request.POST.get("planned_hours") or "").strip()
            starts_on = (request.POST.get("starts_on") or "").strip() or None
            ends_on = (request.POST.get("ends_on") or "").strip() or None
            assignment_status = (request.POST.get("status") or "").strip() or None

            if not room_label:
                raise ValidationError("La salle est obligatoire pour cette affectation.")
            if not planned_hours_raw:
                raise ValidationError("Le volume horaire est obligatoire pour cette affectation.")
            academic_class = AcademicClass.objects.filter(id=class_id, is_active=True).first() if class_id else None
            semester = Semester.objects.filter(id=semester_id, academic_class__is_active=True).first() if semester_id else None
            ue = UE.objects.filter(id=ue_id, semester__academic_class__is_active=True).first() if ue_id else None
            ec_obj = EC.objects.filter(id=ec_id).select_related("ue", "ue__semester", "ue__semester__academic_class").first() if ec_id else None
            target_branch = branch
            if target_branch is None:
                target_branch = (
                    academic_class.branch if academic_class else
                    semester.academic_class.branch if semester else
                    ue.semester.academic_class.branch if ue else
                    ec_obj.ue.semester.academic_class if ec_obj else None
                )
            if target_branch is None:
                raise ValidationError("Cible pédagogique introuvable.")
            payload = {
                "actor": request.user,
                "teacher": teacher,
                "branch": target_branch,
                "academic_class": academic_class,
                "semester": semester,
                "ue": ue,
                "ec": ec_obj,
                "room_label": room_label,
                "planned_hours": planned_hours_raw,
                "starts_on": starts_on,
                "ends_on": ends_on,
                "status": assignment_status or DirectorTeacherAssignment.STATUS_ACTIVE,
                "created_by": request.user,
            }
            if assignment is not None:
                result = update_teacher_assignment(assignment=assignment, **payload)
                assignment = result.assignment
                created = False
            else:
                result = create_teacher_assignment(**payload)
                assignment = result.assignment
                created = True
            toast = {
                "level": "success",
                "message": (
                    f"Affectation mise a jour : {assignment.academic_class.display_name} -> {room_label}, {planned_hours_raw} h."
                    if not created
                    else f"Affectation enregistree : {assignment.academic_class.display_name} -> {room_label}, {planned_hours_raw} h."
                ),
            }

        params = request.GET.copy()
        params["section"] = "enseignants"
        request.GET = params
        response = render(
            request,
            "portal/staff/director/partials/workspace.html",
            _build_director_workspace_context(request, toast=toast),
        )
        response["HX-Trigger"] = "director-modal-close"
        return response

    except ValidationError as exc:
        toast = {"level": "error", "message": " ".join(getattr(exc, "messages", [])) or str(exc)}

    params = request.GET.copy()
    params["section"] = "enseignants"
    request.GET = params
    context = _build_director_workspace_context(request, toast=toast)
    return render(request, "portal/staff/director/partials/workspace.html", context)


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_teacher_assign(request):
    branch = _resolve_director_branch(request)
    if branch is None:
        return HttpResponseBadRequest("Aucune annexe.")

    User = get_user_model()
    raw_teacher_id = (request.GET.get("teacher_id") or request.POST.get("teacher_id") or "").strip()
    teacher = None
    if raw_teacher_id.isdigit():
        teacher = User.objects.select_related("profile", "profile__branch").filter(
            pk=int(raw_teacher_id),
            is_active=True,
            profile__position="teacher",
            profile__branch=branch,
        ).first()

    raw_assignment_id = (request.GET.get("assignment_id") or request.POST.get("assignment_id") or "").strip()
    assignment = None
    if raw_assignment_id.isdigit() and teacher is not None:
        assignment = DirectorTeacherAssignment.objects.select_related(
            "academic_class", "ec"
        ).filter(
            pk=int(raw_assignment_id), teacher=teacher, branch=branch, is_active=True
        ).first()

    existing = list(
        DirectorTeacherAssignment.objects.select_related("academic_class", "ec").filter(
            teacher=teacher, branch=branch, is_active=True
        ).order_by("-created_at", "-id")
    ) if teacher else []

    if request.method == "GET":
        if assignment is None and existing:
            assignment = existing[0]
        return render(
            request,
            "portal/staff/director/modals/teacher_assign_modal.html",
            {
                "assign_teacher": teacher,
                "assign_existing": existing,
                "assign_assignment": assignment,
                "assignment_form": DirectorTeacherAssignmentForm(branch=branch, instance=assignment),
            },
        )
    if request.method != "POST":
        return _deny_portal_access(request)

    action = (request.POST.get("action") or "add").strip().lower()
    form = DirectorTeacherAssignmentForm(request.POST, branch=branch, instance=assignment)
    if teacher is None:
        form.add_error(None, "Enseignant introuvable.")
        return render(
            request,
            "portal/staff/director/modals/teacher_assign_modal.html",
            {"assign_teacher": None, "assign_existing": [], "assign_assignment": None, "assignment_form": form},
        )

    try:
        if action in {"remove", "archive"}:
            if assignment is None:
                raise ValidationError("Affectation introuvable.")
            archive_teacher_assignment(actor=request.user, assignment=assignment, branch=branch)
            toast = {"level": "success", "message": "Affectation retiree."}
        elif action == "suspend":
            if assignment is None:
                raise ValidationError("Affectation introuvable.")
            suspend_teacher_assignment(actor=request.user, assignment=assignment, branch=branch)
            toast = {"level": "success", "message": "Affectation suspendue."}
        elif action == "activate":
            if assignment is None:
                raise ValidationError("Affectation introuvable.")
            activate_teacher_assignment(actor=request.user, assignment=assignment, branch=branch)
            toast = {"level": "success", "message": "Affectation activee."}
        else:
            if not form.is_valid():
                return render(
                    request,
                    "portal/staff/director/modals/teacher_assign_modal.html",
                    {
                        "assign_teacher": teacher,
                        "assign_existing": existing,
                        "assign_assignment": assignment,
                        "assignment_form": form,
                        "toast": {"level": "error", "message": "Corrigez les champs signalés."},
                    },
                )
            values = form.cleaned_data
            payload = {
                "actor": request.user,
                "teacher": teacher,
                "branch": branch,
                "academic_class": values["class_id"],
                "ec": values["ec_id"],
                "room_label": values["room_label"],
                "planned_hours": str(values["planned_hours"]),
                "starts_on": values["starts_on"].isoformat() if values["starts_on"] else None,
                "ends_on": values["ends_on"].isoformat() if values["ends_on"] else None,
            }
            if assignment is not None:
                if values["ec_id"] is None:
                    assignment.ec = None
                    assignment.ue = None
                    assignment.semester = None
                if values["starts_on"] is None:
                    assignment.starts_on = None
                if values["ends_on"] is None:
                    assignment.ends_on = None
                result = update_teacher_assignment(assignment=assignment, **payload)
                prefix = "Affectation mise a jour"
            else:
                result = create_teacher_assignment(created_by=request.user, **payload)
                prefix = "Affectation enregistree"
            toast = {
                "level": "success",
                "message": (
                    f"{prefix} : {result.assignment.academic_class.display_name} -> "
                    f"{values['room_label']}, {values['planned_hours']} h."
                ),
            }
    except ValidationError as exc:
        form.add_error(None, " ".join(getattr(exc, "messages", [])) or str(exc))
        return render(
            request,
            "portal/staff/director/modals/teacher_assign_modal.html",
            {
                "assign_teacher": teacher,
                "assign_existing": existing,
                "assign_assignment": assignment,
                "assignment_form": form,
                "toast": {"level": "error", "message": "Action impossible."},
            },
        )

    response = _render_director_subview(
        request,
        section="enseignants",
        subview="assignments",
        template_name=_TEACHER_SUBVIEW_TEMPLATES["assignments"],
        toast=toast,
    )
    response["HX-Retarget"] = "#director-teacher-subcontent"
    response["HX-Trigger"] = "director-modal-close"
    return response


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_teacher_profile(request, teacher_id: int):
    from portal.services.director.teacher_profile_service import build_teacher_profile_context
    branch = _resolve_director_branch(request)
    User = get_user_model()
    teacher = User.objects.select_related("profile", "profile__branch").filter(
        id=teacher_id,
        is_active=True,
        profile__position="teacher",
    )
    if branch is not None:
        teacher = teacher.filter(profile__branch=branch)
    teacher = teacher.first()
    if not teacher:
        return render(request, "portal/staff/director/partials/drawers/teacher_profile_drawer.html", {
            "toast": {"level": "error", "message": "Enseignant introuvable ou hors annexe."}
        })
    ctx = build_teacher_profile_context(teacher=teacher, branch=branch)
    return render(request, "portal/staff/director/partials/drawers/teacher_profile_drawer.html", ctx)


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_teacher_contract_download(request, teacher_id: int):
    branch = _resolve_director_branch(request)
    User = get_user_model()
    teacher = User.objects.select_related("profile", "profile__branch").filter(
        id=teacher_id,
        profile__position="teacher",
    ).first()
    if teacher is None:
        return HttpResponseBadRequest("Enseignant introuvable.")
    if branch is not None and getattr(getattr(teacher, "profile", None), "branch_id", None) != branch.id:
        return HttpResponseForbidden("Acces inter-annexes refuse.")

    try:
        pdf_bytes = generate_teacher_contract_pdf(teacher)
    except Exception as exc:
        return HttpResponseBadRequest(str(exc) or "Generation du contrat impossible.")

    filename = f"contrat-enseignant-{teacher.username}.pdf"
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_teacher_document_upload(request):
    branch = _resolve_director_branch(request)
    if branch is None:
        return HttpResponseBadRequest("Aucune annexe.")
    teacher_id_raw = (request.GET.get("teacher_id") or request.POST.get("teacher_id") or "").strip()
    teacher_id = int(teacher_id_raw) if teacher_id_raw.isdigit() else None

    if request.method == "GET":
        return render(
            request,
            "portal/staff/director/modals/teacher_document_upload_modal.html",
            {"teacher_document_form": DirectorTeacherDocumentForm(
                branch=branch, selected_teacher_id=teacher_id
            )},
        )
    if request.method != "POST":
        return _deny_portal_access(request)

    form = DirectorTeacherDocumentForm(request.POST, request.FILES, branch=branch)
    if not form.is_valid():
        return render(
            request,
            "portal/staff/director/modals/teacher_document_upload_modal.html",
            {"teacher_document_form": form, "toast": {"level": "error", "message": "Corrigez les champs signalés."}},
        )
    try:
        values = form.cleaned_data
        upload_teacher_document(
            user=request.user,
            teacher_id=values["teacher_id"].pk,
            document_type=values["document_type"],
            file=values["file"],
            note=values["note"],
        )
    except ValidationError as exc:
        form.add_error(None, " ".join(exc.messages) or "Upload impossible.")
        return render(
            request,
            "portal/staff/director/modals/teacher_document_upload_modal.html",
            {"teacher_document_form": form, "toast": {"level": "error", "message": "Upload impossible."}},
        )

    response = _render_director_subview(
        request,
        section="enseignants",
        subview="files",
        template_name=_TEACHER_SUBVIEW_TEMPLATES["files"],
        toast={"level": "success", "message": "Piece enseignant televersee."},
    )
    response["HX-Retarget"] = "#director-teacher-subcontent"
    response["HX-Trigger"] = "director-modal-close"
    return response


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_teacher_documents_modal(request):
    branch = _resolve_director_branch(request)
    User = get_user_model()
    teacher_id_raw = (request.GET.get("teacher_id") or "").strip()
    teacher_id = int(teacher_id_raw) if teacher_id_raw.isdigit() else None

    teacher_rows = list(
        User.objects.select_related("profile")
        .filter(is_active=True, profile__position="teacher", profile__branch=branch)
        .order_by("first_name", "last_name")
    ) if branch else []
    selected_teacher = next((t for t in teacher_rows if t.id == teacher_id), teacher_rows[0] if teacher_rows else None)
    teacher_documents = list(
        TeacherDocument.objects.select_related("teacher", "uploaded_by", "verified_by")
        .filter(branch=branch, teacher=selected_teacher)
        .order_by("-created_at", "-id")
    ) if selected_teacher else []

    return render(
        request,
        "portal/staff/director/modals/teacher_documents_modal.html",
        {
            "document_teacher_rows": teacher_rows,
            "selected_document_teacher": selected_teacher,
            "teacher_documents": teacher_documents,
            "teacher_document_type_choices": TeacherDocument.DOCUMENT_CHOICES,
        },
    )


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_transfer_create(request):
    branch = _resolve_director_branch(request)
    form = DirectorTransferForm(
        request.POST or None,
        request.FILES or None,
        branch=branch,
        initial={"transfer_type": TransferRequest.TYPE_INTERNAL},
    )
    if request.method == "POST" and form.is_valid():
        try:
            create_transfer_request(
                user=request.user,
                enrollment_id=getattr(form.cleaned_data.get("enrollment_id"), "pk", None),
                transfer_type=form.cleaned_data["transfer_type"],
                target_class_id=getattr(form.cleaned_data.get("target_class_id"), "pk", None),
                target_school_name=form.cleaned_data.get("target_school_name"),
                reason=form.cleaned_data["reason"],
                attachment=form.cleaned_data.get("attachment"),
                transfer_data={
                    key: form.cleaned_data.get(key)
                    for key in (
                        "school_city", "destination_programme", "destination_level",
                        "academic_check_completed", "administrative_check_completed",
                        "financial_check_completed", "origin_school_name", "first_name",
                        "last_name", "birth_date", "birth_place", "gender", "phone",
                        "email", "address", "city", "country", "equivalence_notes",
                        "academic_decision_reference",
                    )
                },
            )
        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))
        else:
            response = _render_director_subview(
                request,
                section="transferts",
                subview="pending",
                template_name=_TRANSFER_SUBVIEW_TEMPLATES["pending"],
                toast={"level": "success", "message": "Demande de transfert enregistrée."},
            )
            response["HX-Retarget"] = "#director-transfer-subcontent"
            response["HX-Trigger"] = _director_account_hx_trigger(
                "Demande de transfert enregistrée.", extra={"director-modal-close": True}
            )
            return response
    if request.method not in {"GET", "POST"}:
        return _deny_portal_access(request)
    return render(
        request,
        "portal/staff/director/modals/transfer_create_modal.html",
        {"transfer_form": form},
    )


def _director_transfer_detail_response(request, transfer_id, *, toast=None):
    transfer = get_transfer_request_for_director(user=request.user, transfer_id=transfer_id)
    return render(
        request,
        "portal/staff/director/partials/transfers/detail_drawer.html",
        {
            "transfer": transfer,
            "transfer_document_form": DirectorTransferDocumentForm(),
            "toast": toast,
        },
    )


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_transfer_detail(request, pk):
    try:
        return _director_transfer_detail_response(request, pk)
    except ValidationError as exc:
        return HttpResponseBadRequest(" ".join(exc.messages))


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
@require_POST
def director_transfer_document_upload(request, pk):
    form = DirectorTransferDocumentForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            add_transfer_document(
                user=request.user,
                transfer_id=pk,
                document_type=form.cleaned_data["document_type"],
                title=form.cleaned_data["title"],
                file=form.cleaned_data["file"],
            )
        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))
        else:
            return _director_transfer_detail_response(
                request,
                pk,
                toast={"level": "success", "message": "Pièce ajoutée au dossier."},
            )
    try:
        transfer = get_transfer_request_for_director(user=request.user, transfer_id=pk)
    except ValidationError as exc:
        return HttpResponseBadRequest(" ".join(exc.messages))
    return render(
        request,
        "portal/staff/director/partials/transfers/detail_drawer.html",
        {"transfer": transfer, "transfer_document_form": form},
    )


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
@require_POST
def director_transfer_document_review(request, pk):
    try:
        document = review_transfer_document(
            user=request.user,
            document_id=pk,
            action=request.POST.get("action"),
        )
        return _director_transfer_detail_response(
            request,
            document.transfer_request_id,
            toast={"level": "success", "message": "État de la pièce mis à jour."},
        )
    except ValidationError as exc:
        return HttpResponseBadRequest(" ".join(exc.messages))


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_teacher_document_review(request):
    branch = _resolve_director_branch(request)
    if request.method != "POST":
        return _deny_portal_access(request)

    toast = {"level": "error", "message": "Decision sur la piece impossible."}
    try:
        document_raw = (request.POST.get("document_id") or "").strip()
        document_id = int(document_raw) if document_raw.isdigit() else None
        action = (request.POST.get("action") or "").strip().lower()
        if document_id is None:
            raise ValidationError("Document introuvable.")
        if action not in {"verify", "unverify"}:
            raise ValidationError("Action documentaire inconnue.")
        review_teacher_document(
            user=request.user,
            document_id=document_id,
            verify=action == "verify",
        )
        toast = {"level": "success", "message": "Etat du document mis a jour."}
    except ValidationError as exc:
        toast = {"level": "error", "message": " ".join(exc.messages) or "Decision sur la piece impossible."}

    teacher_id_raw = (request.POST.get("teacher_id") or "").strip()
    User = get_user_model()
    selected_teacher = User.objects.select_related("profile").filter(
        pk=int(teacher_id_raw) if teacher_id_raw.isdigit() else None,
        profile__position="teacher",
        profile__branch=branch,
    ).first()
    teacher_documents = list(
        TeacherDocument.objects.select_related("teacher", "uploaded_by", "verified_by").filter(
            branch=branch, teacher=selected_teacher
        ).order_by("-created_at", "-id")
    ) if selected_teacher else []
    return render(
        request,
        "portal/staff/director/modals/teacher_documents_modal.html",
        {
            "selected_document_teacher": selected_teacher,
            "teacher_documents": teacher_documents,
            "toast": toast,
        },
    )


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_transfer_review(request):
    _resolve_director_branch(request)
    if request.method != "POST":
        return _deny_portal_access(request)

    toast = {"level": "error", "message": "Decision sur le transfert impossible."}
    try:
        transfer_raw = (request.POST.get("transfer_id") or "").strip()
        transfer_id = int(transfer_raw) if transfer_raw.isdigit() else None
        if transfer_id is None:
            raise ValidationError("Demande de transfert introuvable.")
        review_transfer_request(
            user=request.user,
            transfer_id=transfer_id,
            action=request.POST.get("action"),
            decision_note=request.POST.get("decision_note"),
            checks={
                "academic_check_completed": request.POST.get("academic_check_completed") == "on",
                "administrative_check_completed": request.POST.get("administrative_check_completed") == "on",
                "financial_check_completed": request.POST.get("financial_check_completed") == "on",
            },
        )
        toast = {"level": "success", "message": "Demande de transfert mise a jour."}
    except ValidationError as exc:
        toast = {"level": "error", "message": " ".join(exc.messages) or "Decision sur le transfert impossible."}

    response = _render_director_subview(
        request,
        section="transferts",
        subview="pending",
        template_name=_TRANSFER_SUBVIEW_TEMPLATES["pending"],
        toast=toast,
    )
    response["HX-Retarget"] = "#director-transfer-subcontent"
    return response


def _user_initials(display_name: str) -> str:
    parts = [p for p in (display_name or "").strip().split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return (parts[0][:2] if len(parts[0]) > 1 else parts[0] + "?").upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _render_it_dashboard(request, *, initial_module=None, initial_workspace_html=None):
    context = _build_it_dashboard_context(request)
    context.update(
        build_it_grade_selection_context(
            request.user,
            class_id=request.GET.get("class_id"),
            semester_id=request.GET.get("semester_id"),
        )
    )
    initial_module = initial_module or request.GET.get("module") or "home"
    context["initial_module"] = initial_module
    if initial_workspace_html is not None:
        context["initial_workspace_html"] = mark_safe(initial_workspace_html)
    branch = context.get("branch")
    dashboard_url = reverse("accounts_portal:portal_dashboard")
    it_modules = [
        ("home", "Accueil", "home", "accounts_portal:it_home_workspace"),
        ("notes", "Notes et resultats", "file-spreadsheet", "accounts_portal:it_notes_flow_workspace"),
        ("structure", "Parametrage academique", "blocks", "accounts_portal:it_structure_workspace"),
        ("import", "Import / export", "upload-cloud", "accounts_portal:it_import_workspace"),
        ("archives", "Archives", "folder-archive", "accounts_portal:it_archives_workspace"),
        ("cards", "Cartes etudiants", "badge", "accounts_portal:it_cards_workspace"),
        ("accounts", "Utilisateurs", "shield-check", "accounts_portal:it_accounts_flow_workspace"),
        ("support", "Support", "life-buoy", "accounts_portal:it_support_flow_workspace"),
        ("supervision", "Supervision", "alert-triangle", "accounts_portal:it_supervision_workspace"),
        ("audit", "Journal d'audit", "history", "accounts_portal:it_audit_workspace"),
        ("catalog", "Catalogue", "library", "accounts_portal:it_catalog_workspace"),
        ("notifications", "Notifications", "bell", "accounts_portal:it_notifications_workspace"),
        ("settings", "Compte", "settings", "accounts_portal:it_my_account_workspace"),
    ]
    module_items = []
    for key, label, icon, url_name in it_modules:
        module_items.append(
            {
                "key": key,
                "label": label,
                "icon": icon,
                "url": f"{dashboard_url}?module={key}",
                "hx_get": reverse(url_name),
                "hx_target": "#it-workspace",
                "hx_push_url": f"{dashboard_url}?module={key}",
            }
        )
    context.update(
        build_role_dashboard_shell(
            request,
            role="it_support",
            key="it-dashboard",
            title="Administration IT",
            subtitle="Support et qualite des donnees",
            active_section=initial_module,
            dashboard_url=dashboard_url,
            workspace_target="#it-workspace",
            branch=branch,
            context_label=f"Annexe - {branch.name}" if branch else "Support global",
            groups=[{"label": "Administration IT", "items": module_items}],
            modal_title="Administration technique",
        )
    )
    return render(
        request,
        "portal/informaticien/dashboard.html",
        context,
    )


def _build_it_dashboard_context_for_request(request, overrides=None):
    original_get = request.GET
    if overrides:
        merged = request.GET.copy()
        for key, value in overrides.items():
            if value:
                merged[key] = value
        request.GET = merged
    try:
        return _build_it_dashboard_context(request)
    finally:
        request.GET = original_get


def _get_manageable_target_user(request):
    branch = _resolve_academic_branch(request)
    target_user = request.user.__class__.objects.filter(pk=request.POST.get("target_user_id")).first()
    if target_user is None or not can_manage_user_in_branch(branch=branch, target_user=target_user):
        return branch, None
    return branch, target_user


def _render_it_action_panel(request, *, default_panel="diagnostics"):
    panel = request.POST.get("panel") or default_panel
    context = _build_it_dashboard_context_for_request(
        request,
        overrides={
            "q": request.POST.get("q"),
            "kind": request.POST.get("kind"),
            "id": request.POST.get("id"),
        },
    )
    template_name = (
        "portal/informaticien/partials/accounts_panel.html"
        if panel == "accounts"
        else "portal/informaticien/partials/diagnostics_panel.html"
    )
    return render(request, template_name, context)


@login_required
def portal_home(request):
    return redirect(get_post_login_portal_url(request.user))


@login_required
def portal_dashboard(request):
    position = get_user_position(request.user)

    if position in {"finance_manager", "payment_agent"}:
        return redirect("accounts:finance_dashboard")
    if position == "secretary":
        return redirect("secretary:secretary_dashboard")
    if position == "admissions":
        return redirect("accounts:admissions_dashboard")
    if position == "super_admin" or request.user.is_superuser:
        return redirect("superadmin:dashboard")
    if position in {"executive_director", "deputy_executive_director"}:
        return dg_portal(request)
    if position == "director_of_studies":
        return _render_director_dashboard(request)
    if position == "academic_supervisor":
        from portal.views.supervisor import _render_supervisor_dashboard

        return _render_supervisor_dashboard(request)
    if position == "it_support":
        return _render_it_dashboard(request)
    if position == "marketing_manager":
        return redirect("marketing:dashboard")

    if can_access(request.user, "view_portal", "student"):
        return redirect("portal_student:dashboard")
    if can_access(request.user, "view_portal", "teacher"):
        return teacher_portal(request)
    if can_access(request.user, "view_portal", "staff"):
        return staff_portal(request)
    if request.user.is_superuser:
        return redirect("admin:index")
    return _deny_portal_access(request)


@login_required
def student_portal(request):
    if not can_access(request.user, "view_portal", "student"):
        return _deny_portal_access(request)
    return redirect("accounts_portal:portal_dashboard")


@login_required
def staff_portal(request):
    if not can_access(request.user, "view_portal", "staff"):
        return _deny_portal_access(request)

    context = _build_portal_context(
        request,
        page_title="Portail staff",
        module_cards=[
            "Gestion etudiants",
            "Documents",
            "Admissions",
            "Finance",
            "Secretariat",
            "Supervision academique",
        ],
    )
    return render(request, "portal/staff.html", context)


TEACHER_PORTAL_SECTIONS = (
    "overview",
    "classes",
    "supports",
    "schedule",
    "logs",
    "salary",
    "notifications",
    "settings",
)

TEACHER_SECTION_CONTEXT_BUILDERS = {
    "overview": build_teacher_overview_context,
    "classes": build_teacher_classes_context,
    "supports": build_teacher_supports_context,
    "schedule": build_teacher_schedule_context,
    "logs": build_teacher_logs_context,
    "salary": build_teacher_salary_context,
    "notifications": build_teacher_notifications_context,
    "settings": build_teacher_settings_context,
}


def _teacher_nav_items(active_section):
    definitions = (
        ("overview", "Accueil", "layout-dashboard"),
        ("classes", "Mes classes", "graduation-cap"),
        ("supports", "Supports", "folder-open"),
        ("schedule", "Planning", "calendar-days"),
        ("logs", "Cahier texte", "book-open"),
        ("salary", "Honoraires", "wallet"),
        ("notifications", "Notifications", "bell"),
        ("settings", "Paramètres", "settings"),
    )
    return [
        {
            "id": section,
            "label": label,
            "icon": icon,
            "url": f"?section={section}",
            "hx_get": f"?section={section}",
            "hx_target": "#teacher-workspace",
            "hx_swap": "outerHTML",
            "active": active_section == section,
        }
        for section, label, icon in definitions
    ]


@login_required
def teacher_portal(request):
    if not can_access(request.user, "view_portal", "teacher"):
        return _deny_portal_access(request)

    branch = _resolve_academic_branch(request)
    section = request.GET.get("section", "overview")
    active_section = section if section in TEACHER_PORTAL_SECTIONS else "overview"

    if section == "search":
        q = (request.GET.get("q") or "").strip()
        if branch and len(q) >= 1:
            from students.models import Student

            classes = AcademicClass.objects.filter(
                branch=branch,
            ).filter(
                Q(name__icontains=q) | Q(level__icontains=q) | Q(programme__title__icontains=q)
            )[:5]

            ecs = EC.objects.filter(
                ue__semester__academic_class__branch=branch,
                teachingassignment__teacher__user=request.user,
            ).filter(
                Q(title__icontains=q) | Q(ue__code__icontains=q)
            ).distinct()[:5]

            students = Student.objects.filter(
                inscription__candidature__branch=branch,
                is_active=True,
            ).filter(
                Q(matricule__icontains=q)
                | Q(inscription__candidature__first_name__icontains=q)
                | Q(inscription__candidature__last_name__icontains=q)
            ).distinct()[:5]

            return render(request, "portal/partials/teacher_search_results.html", {
                "q": q,
                "classes": classes,
                "ecs": ecs,
                "students": students,
            })
        return render(request, "portal/partials/teacher_search_results.html", {"q": q})

    if branch is None:
        context = {
            **_build_portal_context(
                request,
                page_title="Dashboard enseignant",
                module_cards=[],
            ),
            "dashboard_kind": "Enseignant",
            "branch": None,
            "branch_missing": True,
            "active_section": active_section,
            "teacher_nav_items": _teacher_nav_items(active_section),
            "status_summary": {"branch_name": "Annexe non définie"},
            "pending_lesson_logs_count": 0,
            "notifications_count": 0,
            "kpi_cards": [],
        }
        return render(request, "portal/teacher/v2/dashboard.html", context)

    context_builder = TEACHER_SECTION_CONTEXT_BUILDERS[active_section]
    context = context_builder(
        request,
        branch=branch,
        base_context_builder=_build_portal_context,
    )
    context["active_section"] = active_section
    context["teacher_nav_items"] = _teacher_nav_items(active_section)
    context.setdefault("pending_lesson_logs_count", 0)
    context["notifications_count"] = get_user_unread_count(
        request.user,
        exclude_sources=TEACHER_EXCLUDED_NOTIFICATION_SOURCES,
    )
    context.setdefault("teacher_notifications", {"unread_count": 0, "items": []})
    context["kpi_cards"] = [
        {"label": "Mes classes", "value": len(context.get("class_focus_rows") or []), "icon": "graduation-cap"},
        {"label": "Cours aujourd'hui", "value": context.get("teacher_kpis", {}).get("today_courses", 0), "icon": "calendar-check-2"},
        {"label": "Cahiers en attente", "value": context.get("pending_lesson_logs_count", 0), "icon": "book-open"},
        {"label": "Cahiers du mois", "value": context.get("teacher_kpis", {}).get("month_done_logs", 0), "icon": "clipboard-check"},
    ]
    teacher_kpis = context.get("teacher_kpis", {})
    support_stats = context.get("teacher_support_stats", {})
    section_kpis = {
        "classes": [
            {"label": "Classes", "value": len(context.get("class_focus_rows") or []), "icon": "graduation-cap", "tone": "primary"},
            {"label": "Matières", "value": teacher_kpis.get("subjects_count", 0), "icon": "book-open", "tone": "info"},
            {"label": "Étudiants", "value": teacher_kpis.get("visible_students", 0), "icon": "users", "tone": "success"},
        ],
        "supports": [
            {"label": "Classes", "value": len(context.get("class_focus_rows") or []), "icon": "graduation-cap", "tone": "primary"},
            {"label": "Chapitres", "value": support_stats.get("chapters", 0), "icon": "book-open", "tone": "info"},
            {"label": "Supports", "value": support_stats.get("contents", 0), "icon": "folder-open", "tone": "success"},
            {"label": "Fichiers", "value": support_stats.get("files", 0), "icon": "file", "tone": "neutral"},
        ],
        "schedule": [
            {"label": "Aujourd'hui", "value": teacher_kpis.get("today_courses", 0), "icon": "calendar-check", "tone": "primary"},
            {"label": "Cette semaine", "value": teacher_kpis.get("week_courses", 0), "icon": "calendar-days", "tone": "success"},
            {"label": "Classes", "value": len(context.get("class_focus_rows") or []), "icon": "graduation-cap", "tone": "info"},
            {"label": "Salles", "value": teacher_kpis.get("weekly_rooms", 0), "icon": "door-open", "tone": "warning"},
        ],
        "logs": [
            {"label": "Récents", "value": len(context.get("recent_lesson_logs") or []), "icon": "book-open", "tone": "success"},
            {"label": "Cette semaine", "value": context.get("week_lesson_logs_count", 0), "icon": "calendar-days", "tone": "primary"},
            {"label": "En attente", "value": context.get("pending_lesson_logs_count", 0), "icon": "alert-triangle", "tone": "warning"},
            {"label": "Ce mois", "value": teacher_kpis.get("month_done_logs", 0), "icon": "clipboard-check", "tone": "info"},
        ],
        "salary": [
            {"label": "Heures ce mois", "value": context.get("teacher_hours", {}).get("month_hours", 0), "icon": "clock", "tone": "primary"},
            {"label": "Total année", "value": context.get("teacher_hours", {}).get("total_hours", 0), "icon": "calendar", "tone": "success"},
            {"label": "En attente", "value": context.get("teacher_payments", {}).get("pending_count", 0), "icon": "hourglass", "tone": "warning"},
            {"label": "Payés", "value": context.get("teacher_payments", {}).get("paid_count", 0), "icon": "circle-check", "tone": "success"},
        ],
    }
    context["section_kpi_cards"] = section_kpis.get(active_section, [])
    if request.headers.get("HX-Request") == "true":
        return render(request, "portal/teacher/v2/workspace.html", context)
    return render(request, "portal/teacher/v2/dashboard.html", context)


@_position_required({"teacher"})
def teacher_class_detail(request, class_id: int):
    branch = _resolve_academic_branch(request)
    try:
        raw_week_start = (request.GET.get("week_start") or "").strip()
        week_start = timezone.localdate()
        if raw_week_start:
            week_start = datetime.strptime(raw_week_start, "%Y-%m-%d").date()
        context = build_teacher_class_detail_context(
            request,
            branch=branch,
            class_id=class_id,
            week_start=week_start,
        )
    except (ValidationError, ValueError) as exc:
        error_message = exc.messages[0] if isinstance(exc, ValidationError) and exc.messages else str(exc)
        context = {
            "toast": {"level": "error", "message": error_message},
            "academic_class": None,
        }
    return render(request, "portal/partials/teacher_class_detail.html", context)


@_position_required({"teacher"})
def teacher_support_workspace(request):
    branch = _resolve_academic_branch(request)

    def _parse_id(raw_value):
        raw_value = (raw_value or "").strip()
        if not raw_value:
            return None
        return int(raw_value)

    class_id = request.POST.get("class_id") if request.method == "POST" else request.GET.get("class_id")
    ec_id = request.POST.get("ec_id") if request.method == "POST" else request.GET.get("ec_id")
    chapter_id = request.POST.get("chapter_id") if request.method == "POST" else request.GET.get("chapter_id")
    support_target = (
        request.POST.get("support_target")
        or request.GET.get("support_target")
        or "#sg-drawer-content"
    ).strip()
    if not support_target.startswith("#"):
        support_target = "#sg-drawer-content"

    try:
        parsed_class_id = _parse_id(class_id)
        parsed_ec_id = _parse_id(ec_id)
        parsed_chapter_id = _parse_id(chapter_id)

        if request.method == "POST":
            context = build_teacher_support_workspace_context(
                request,
                branch=branch,
                class_id=parsed_class_id,
                ec_id=parsed_ec_id,
                chapter_id=parsed_chapter_id,
            )
            context["teacher_support_target"] = support_target
            selected_class = context["selected_class"]
            selected_ec = context["selected_ec"]
            selected_chapter = context["selected_chapter"]
            action = (request.POST.get("action") or "").strip()

            if action in ("edit_content", "delete_content", "fetch_content"):
                content_id = _parse_id(request.POST.get("content_id"))
                if content_id is None:
                    raise ValidationError("Identifiant du contenu manquant.")

                if action == "fetch_content":
                    editing_content = get_teacher_content_for_edit(
                        teacher=request.user,
                        branch=branch,
                        content_id=content_id,
                    )
                    context = build_teacher_support_workspace_context(
                        request, branch=branch,
                        class_id=editing_content["class_id"],
                        ec_id=editing_content.get("ec_id"),
                        chapter_id=editing_content.get("chapter_id"),
                    )
                    context["teacher_support_target"] = support_target
                    context["editing_content"] = editing_content
                    return render(request, "portal/partials/teacher_support_workspace.html", context)

                elif action == "edit_content":
                    edit_content_id = content_id
                    chapter_id_edit = _parse_id(request.POST.get("chapter_id"))
                    updated = update_teacher_content(
                        teacher=request.user,
                        branch=branch,
                        content_id=edit_content_id,
                        title=request.POST.get("content_title"),
                        content_type=request.POST.get("content_type"),
                        chapter_id=chapter_id_edit,
                        file=request.FILES.get("file"),
                        video_url=request.POST.get("video_url"),
                        text_content=request.POST.get("text_content"),
                    )
                    toast_message = f"Support '{updated.title}' modifie avec succes."
                    context = build_teacher_support_workspace_context(
                        request, branch=branch,
                        class_id=parsed_class_id,
                        ec_id=parsed_ec_id,
                        chapter_id=updated.chapter_id,
                        toast={"level": "success", "message": toast_message},
                    )
                    context["teacher_support_target"] = support_target
                    return render(request, "portal/partials/teacher_support_workspace.html", context)

                elif action == "delete_content":
                    deleted = delete_teacher_content(
                        teacher=request.user,
                        branch=branch,
                        content_id=content_id,
                    )
                    toast_message = f"Support '{deleted.title}' supprime avec succes."
                    context = build_teacher_support_workspace_context(
                        request, branch=branch,
                        class_id=parsed_class_id,
                        ec_id=parsed_ec_id,
                        chapter_id=parsed_chapter_id,
                        toast={"level": "success", "message": toast_message},
                    )
                    context["teacher_support_target"] = support_target
                    return render(request, "portal/partials/teacher_support_workspace.html", context)

            if selected_class is None:
                raise ValidationError("Aucune classe disponible pour ce compte.")
            if selected_ec is None:
                raise ValidationError("Selectionnez d'abord une matiere.")

            toast_message = "Support enregistre avec succes."
            if action == "create_chapter":
                chapter_title = (request.POST.get("chapter_title") or "").strip()
                if not chapter_title:
                    raise ValidationError("Le titre du chapitre est obligatoire.")
                chapter_order = selected_ec.chapters.count() + 1
                created_chapter = ECChapter.objects.create(
                    ec=selected_ec,
                    title=chapter_title,
                    order=chapter_order,
                )
                parsed_chapter_id = created_chapter.id
                toast_message = f"Chapitre '{chapter_title}' cree avec succes."
            elif action == "create_content":
                new_chapter_title = (request.POST.get("new_chapter_title") or "").strip()
                chapter_selection_blank = not (request.POST.get("chapter_id") or "").strip()
                if new_chapter_title:
                    selected_chapter = ECChapter.objects.create(
                        ec=selected_ec,
                        title=new_chapter_title,
                        order=selected_ec.chapters.count() + 1,
                    )
                    parsed_chapter_id = selected_chapter.id
                elif chapter_selection_blank:
                    selected_chapter = selected_ec.chapters.filter(title="Supports de cours").first()
                    if selected_chapter is None:
                        selected_chapter = ECChapter.objects.create(
                            ec=selected_ec,
                            title="Supports de cours",
                            order=selected_ec.chapters.count() + 1,
                        )
                    parsed_chapter_id = selected_chapter.id
                elif selected_chapter is None:
                    selected_chapter = ECChapter.objects.create(
                        ec=selected_ec,
                        title="Supports de cours",
                        order=selected_ec.chapters.count() + 1,
                    )
                    parsed_chapter_id = selected_chapter.id
                content_title = (request.POST.get("content_title") or "").strip()
                if not content_title:
                    raise ValidationError("Le titre du support est obligatoire.")
                content_type = (request.POST.get("content_type") or "").strip()
                allowed_types = {choice[0] for choice in ECContent.CONTENT_TYPE_CHOICES}
                if content_type not in allowed_types:
                    raise ValidationError("Type de contenu invalide.")

                uploaded_file = request.FILES.get("file")
                video_url = (request.POST.get("video_url") or "").strip() or None
                text_content = (request.POST.get("text_content") or "").strip()

                if content_type == ECContent.CONTENT_TYPE_TEXT:
                    if uploaded_file is not None:
                        raise ValidationError("Le type Texte n'accepte pas de fichier.")
                    if video_url:
                        raise ValidationError("Le type Texte n'accepte pas d'URL video.")
                    if not text_content:
                        raise ValidationError("Le texte du support est obligatoire pour ce type de contenu.")
                elif content_type == ECContent.CONTENT_TYPE_VIDEO:
                    if text_content:
                        raise ValidationError("Le type Video n'accepte pas de texte direct.")
                    if not uploaded_file and not video_url:
                        raise ValidationError("Ajoutez un fichier video ou une URL YouTube.")
                else:
                    if video_url:
                        raise ValidationError("L'URL video est reservee au type Video.")
                    if text_content:
                        raise ValidationError("Le texte direct est reserve au type Texte.")
                    if uploaded_file is None:
                        raise ValidationError("Ajoutez le fichier du support.")

                _validate_content_file_extension(content_type=content_type, uploaded_file=uploaded_file)

                content_order = selected_chapter.contents.count() + 1
                content = ECContent(
                    chapter=selected_chapter,
                    title=content_title,
                    content_type=content_type,
                    file=uploaded_file,
                    video_url=video_url,
                    text_content=text_content,
                    order=content_order,
                )
                content.full_clean()
                content.save()
                toast_message = f"Support '{content_title}' ajoute avec succes."
            else:
                raise ValidationError("Action support inconnue.")

            context = build_teacher_support_workspace_context(
                request,
                branch=branch,
                class_id=selected_class.id,
                ec_id=selected_ec.id,
                chapter_id=parsed_chapter_id or getattr(selected_chapter, "id", None),
                toast={"level": "success", "message": toast_message},
            )
            context["teacher_support_target"] = support_target
            return render(request, "portal/partials/teacher_support_workspace.html", context)

        context = build_teacher_support_workspace_context(
            request,
            branch=branch,
            class_id=parsed_class_id,
            ec_id=parsed_ec_id,
            chapter_id=parsed_chapter_id,
        )
        context["teacher_support_target"] = support_target
    except (ValidationError, ValueError, TypeError) as exc:
        error_message = exc.messages[0] if isinstance(exc, ValidationError) and exc.messages else str(exc)
        try:
            context = build_teacher_support_workspace_context(
                request,
                branch=branch,
                class_id=None,
                ec_id=None,
                chapter_id=None,
                toast={"level": "error", "message": error_message},
            )
            context["teacher_support_target"] = support_target
        except ValidationError:
            context = {
                "branch": branch,
                "toast": {"level": "error", "message": error_message},
                "teacher_support_target": support_target,
                "teacher_support_classes": [],
                "selected_class": None,
                "selected_ec": None,
                "selected_ec_summary": None,
                "selected_chapter": None,
                "teacher_support_ecs": [],
                "teacher_support_chapters": [],
                "teacher_support_contents": [],
                "content_type_choices": ECContent.CONTENT_TYPE_CHOICES,
                "file_content_type_choices": [
                    choice for choice in ECContent.CONTENT_TYPE_CHOICES
                    if choice[0] != ECContent.CONTENT_TYPE_TEXT
                ],
            }
    return render(request, "portal/partials/teacher_support_workspace.html", context)


@_position_required({"teacher"})
def teacher_settings_workspace(request):
    branch = _resolve_academic_branch(request)
    if branch is None:
        return render(
            request,
            "portal/teacher/partials/settings_workspace.html",
            {
                "toast": {"level": "error", "message": "Aucune annexe rattachee a ce compte enseignant."},
                "teacher_dashboard_preference": {
                    "dark_mode": False,
                    "sidebar_collapsed": False,
                    "compact_mode": False,
                    "default_section": "overview",
                    "notify_lesson_reminders": True,
                    "notify_schedule_changes": True,
                    "notify_support_messages": True,
                },
                "teacher_preferences_choices": [],
                "status_summary": {
                    "employment_status": "Inconnu",
                    "employee_code": "Non renseigne",
                    "branch_name": "Non rattache",
                    "hire_date": None,
                },
                "teacher_settings_stats": {"active_classes": 0, "display_mode": "Standard"},
            },
        )

    toast = None
    if request.method == "POST":
        try:
            update_teacher_dashboard_preference(
                actor=request.user,
                teacher=request.user,
                branch=branch,
                dark_mode=request.POST.get("dark_mode") == "on",
                sidebar_collapsed=request.POST.get("sidebar_collapsed") == "on",
                compact_mode=request.POST.get("compact_mode") == "on",
                default_section=request.POST.get("default_section"),
                notify_lesson_reminders=request.POST.get("notify_lesson_reminders") == "on",
                notify_schedule_changes=request.POST.get("notify_schedule_changes") == "on",
                notify_support_messages=request.POST.get("notify_support_messages") == "on",
            )
            toast = {"level": "success", "message": "Parametres enregistres."}
        except ValidationError as exc:
            toast = {"level": "error", "message": exc.messages[0] if getattr(exc, "messages", None) else str(exc)}

    context = build_teacher_settings_context(
        request,
        branch=branch,
        base_context_builder=_build_portal_context,
    )
    context["toast"] = toast
    return render(request, "portal/teacher/partials/settings_workspace.html", context)


@_position_required({"teacher"})
def teacher_content_viewer(request, content_id: int):
    branch = _resolve_academic_branch(request)
    if branch is None:
        return render(
            request,
            "portal/partials/teacher_content_viewer.html",
            {"content": None, "error": "Aucune annexe rattachée à ce compte enseignant."},
        )
    try:
        get_teacher_content_for_edit(
            teacher=request.user,
            branch=branch,
            content_id=content_id,
        )
        content = ECContent.objects.select_related("chapter__ec").get(
            pk=content_id,
            is_active=True,
        )
        if content.chapter is None:
            raise ValidationError("Ce contenu n'est pas rattache a un chapitre.")
        ec = content.chapter.ec
        branch_match = ec.ue.semester.academic_class.branch_id == branch.id
        if not branch_match:
            raise ValidationError("Contenu non accessible pour cette annexe.")

        if content.content_type == ECContent.CONTENT_TYPE_TEXT:
            rendered_text = content.text_content
        else:
            rendered_text = ""

        context = {
            "content": content,
            "rendered_text": rendered_text,
            "branch": branch,
        }
    except (ValidationError, ECContent.DoesNotExist) as exc:
        error_message = exc.messages[0] if isinstance(exc, ValidationError) and exc.messages else str(exc)
        context = {
            "content": None,
            "error": error_message,
        }
    return render(request, "portal/partials/teacher_content_viewer.html", context)


@_position_required({"teacher"})
def teacher_lesson_log_panel(request, event_id: int):
    branch = _resolve_academic_branch(request)

    if request.method == "POST":
        allowed_statuses = {
            LessonLog.STATUS_DONE,
            LessonLog.STATUS_CANCELLED,
            LessonLog.STATUS_PLANNED,
        }
        try:
            context = build_teacher_lesson_log_context(
                request,
                branch=branch,
                event_id=event_id,
            )
            schedule_event = context["schedule_event"]
            status = (request.POST.get("status") or "").strip()
            if status not in allowed_statuses:
                raise ValidationError("Statut de cahier invalide.")
            payload = {
                "status": status,
                "content": request.POST.get("content", ""),
                "homework": request.POST.get("homework", ""),
                "observations": request.POST.get("observations", ""),
            }
            lesson_log = context["lesson_log"]
            if lesson_log is None:
                create_lesson_log(
                    academic_class=schedule_event.academic_class,
                    ec=schedule_event.ec,
                    teacher=schedule_event.teacher,
                    date=timezone.localdate(schedule_event.start_datetime),
                    start_time=timezone.localtime(schedule_event.start_datetime).time(),
                    end_time=timezone.localtime(schedule_event.end_datetime).time(),
                    branch=schedule_event.branch,
                    created_by=request.user,
                    schedule_event=schedule_event,
                    **payload,
                )
            else:
                update_lesson_log(
                    lesson_log,
                    updated_by=request.user,
                    **payload,
                )

            mark_present = request.POST.get("mark_present") == "1"
            if mark_present:
                TeacherAttendance.objects.update_or_create(
                    teacher=request.user,
                    schedule_event=schedule_event,
                    branch=schedule_event.branch,
                    defaults={
                        "date": timezone.localdate(schedule_event.start_datetime),
                        "status": TeacherAttendance.STATUS_PRESENT,
                        "recorded_by": request.user,
                    },
                )
            else:
                TeacherAttendance.objects.filter(
                    teacher=request.user,
                    schedule_event=schedule_event,
                ).delete()

            context = build_teacher_lesson_log_context(
                request,
                branch=branch,
                event_id=event_id,
                toast={"level": "success", "message": "Cahier enregistre avec succes."},
            )
        except ValidationError as exc:
            error_message = exc.messages[0] if exc.messages else str(exc)
            try:
                context = build_teacher_lesson_log_context(
                    request,
                    branch=branch,
                    event_id=event_id,
                    toast={"level": "error", "message": error_message},
                )
            except ValidationError:
                context = {
                    "toast": {"level": "error", "message": error_message},
                    "schedule_event": None,
                    "lesson_log": None,
                    "lesson_log_status_choices": [],
                }
            return render(request, "portal/partials/teacher_lesson_log_panel.html", context)

        return render(request, "portal/partials/teacher_lesson_log_panel.html", context)

    try:
        context = build_teacher_lesson_log_context(
            request,
            branch=branch,
            event_id=event_id,
        )
    except ValidationError as exc:
        error_message = exc.messages[0] if exc.messages else str(exc)
        context = {
            "toast": {"level": "error", "message": error_message},
            "schedule_event": None,
            "lesson_log": None,
            "lesson_log_status_choices": [],
        }
    return render(request, "portal/partials/teacher_lesson_log_panel.html", context)


@_position_required({"teacher"})
def teacher_declare_absence(request, event_id: int):
    """Déclare une absence enseignant pour une séance donnée (HTMX)."""
    branch = _resolve_academic_branch(request)

    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    try:
        declare_teacher_absence_for_event(
            teacher=request.user,
            branch=branch,
            event_id=event_id,
        )
        response = HttpResponse("")
        response["HX-Trigger"] = json.dumps({
            "teacher-toast": {"message": "Absence declaree. Le secretariat est informe.", "type": "warning"},
            "teacher-dashboard-refresh": True,
        })
        return response
    except ValidationError as exc:
        error_message = exc.messages[0] if exc.messages else str(exc)
        response = HttpResponse(error_message, status=400)
        response["HX-Trigger"] = json.dumps({
            "teacher-toast": {"message": error_message, "type": "error"},
        })
        return response


@_position_required({"finance_manager", "payment_agent"})
def finance_portal(request):
    from accounts.dashboards.finance_dashboard import finance_dashboard

    return finance_dashboard(request)


@_position_required({"secretary"})
def secretary_portal(request):
    from secretary.views import secretary_dashboard

    return secretary_dashboard(request)


@_position_required({"admissions"})
def admissions_portal(request):
    from accounts.dashboards.admissions_dashboard import admissions_dashboard

    return admissions_dashboard(request)


@_position_required({"director_of_studies", "executive_director", "deputy_executive_director", "super_admin"})
def director_portal(request):
    if is_global_academic_user(request.user):
        return _render_director_dashboard(request)
    return redirect("accounts_portal:portal_dashboard")


@_position_required({"it_support"})
def it_portal(request):
    return redirect("accounts_portal:portal_dashboard")


@_position_required({"it_support"})
def it_toggle_account(request):
    if request.method != "POST":
        return _deny_portal_access(request)

    branch = _resolve_academic_branch(request)
    target_user = get_scoped_staff_queryset(branch=branch).filter(pk=request.POST.get("target_user_id")).first()
    if target_user is None:
        target_user = request.user.__class__.objects.filter(pk=request.POST.get("target_user_id")).first()

    if target_user is None or not can_manage_user_in_branch(branch=branch, target_user=target_user):
        _store_it_support_feedback(
            request,
            level="error",
            title="Action refusee",
            message="Le compte cible est introuvable ou hors du perimetre de cette annexe.",
        )
        return _redirect_it_dashboard(request)

    if target_user == request.user:
        _store_it_support_feedback(
            request,
            level="error",
            title="Action refusee",
            message="Le compte informaticien courant ne peut pas etre desactive depuis ce dashboard.",
        )
        return _redirect_it_dashboard(request)

    target_user.is_active = not target_user.is_active
    target_user.save(update_fields=["is_active"])
    action_type = (
        "account_activated"
        if target_user.is_active
        else "account_deactivated"
    )
    log_support_action(
        actor=request.user,
        branch=branch,
        action_type=action_type,
        target_user=target_user,
        target_label=target_user.get_full_name() or target_user.username,
        details=f"Activation modifiee via dashboard IT ({branch.name if branch else 'global'}).",
    )
    _store_it_support_feedback(
        request,
        level="success",
        title="Compte mis a jour",
        message=f"Le compte {target_user.get_full_name() or target_user.username} est maintenant {'actif' if target_user.is_active else 'inactif'}.",
    )
    if request.headers.get("HX-Request") == "true":
        panel = request.POST.get("panel") or "diagnostics"
        context = _build_it_dashboard_context_for_request(
            request,
            overrides={
                "q": request.POST.get("q"),
                "kind": request.POST.get("kind"),
                "id": request.POST.get("id"),
            },
        )
        template_name = (
            "portal/informaticien/partials/accounts_panel.html"
            if panel == "accounts"
            else "portal/informaticien/partials/diagnostics_panel.html"
        )
        return render(request, template_name, context)
    return _redirect_it_dashboard(request)


@_position_required({"it_support"})
def it_reset_password(request):
    if request.method != "POST":
        return _deny_portal_access(request)

    branch = _resolve_academic_branch(request)
    target_user = request.user.__class__.objects.filter(pk=request.POST.get("target_user_id")).first()
    if target_user is None or not can_manage_user_in_branch(branch=branch, target_user=target_user):
        _store_it_support_feedback(
            request,
            level="error",
            title="Action refusee",
            message="Le compte cible est introuvable ou hors du perimetre de cette annexe.",
        )
        return _redirect_it_dashboard(request)

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
        details=f"Mot de passe reinitialise via dashboard IT ({branch.name if branch else 'global'}).",
    )
    _store_it_support_feedback(
        request,
        level="success",
        title="Mot de passe reinitialise",
        message=f"Un mot de passe temporaire a ete genere pour {target_user.get_full_name() or target_user.username}.",
        password=temp_password,
    )
    if request.headers.get("HX-Request") == "true":
        panel = request.POST.get("panel") or "diagnostics"
        context = _build_it_dashboard_context_for_request(
            request,
            overrides={
                "q": request.POST.get("q"),
                "kind": request.POST.get("kind"),
                "id": request.POST.get("id"),
            },
        )
        template_name = (
            "portal/informaticien/partials/accounts_panel.html"
            if panel == "accounts"
            else "portal/informaticien/partials/diagnostics_panel.html"
        )
        return render(request, template_name, context)
    return _redirect_it_dashboard(request)


@_position_required({"it_support"})
def it_suspend_account(request):
    if request.method != "POST":
        return _deny_portal_access(request)

    branch, target_user = _get_manageable_target_user(request)
    if target_user is None:
        _store_it_support_feedback(
            request,
            level="error",
            title="Action refusee",
            message="Le compte cible est introuvable ou hors du perimetre de cette annexe.",
        )
        return _redirect_it_dashboard(request)
    if target_user == request.user:
        _store_it_support_feedback(
            request,
            level="error",
            title="Action refusee",
            message="Le compte informaticien courant ne peut pas etre suspendu depuis ce dashboard.",
        )
        return _redirect_it_dashboard(request)

    suspend_account(
        actor=request.user,
        branch=branch,
        target_user=target_user,
        reason=request.POST.get("reason"),
    )
    _store_it_support_feedback(
        request,
        level="success",
        title="Compte suspendu",
        message=f"Le compte {target_user.get_full_name() or target_user.username} est suspendu et ne peut plus se connecter.",
    )
    if request.headers.get("HX-Request") == "true":
        return _render_it_action_panel(request)
    return _redirect_it_dashboard(request)


@_position_required({"it_support"})
def it_reactivate_account(request):
    if request.method != "POST":
        return _deny_portal_access(request)

    branch, target_user = _get_manageable_target_user(request)
    if target_user is None:
        _store_it_support_feedback(
            request,
            level="error",
            title="Action refusee",
            message="Le compte cible est introuvable ou hors du perimetre de cette annexe.",
        )
        return _redirect_it_dashboard(request)

    reactivate_account(actor=request.user, branch=branch, target_user=target_user)
    _store_it_support_feedback(
        request,
        level="success",
        title="Compte reactive",
        message=f"Le compte {target_user.get_full_name() or target_user.username} est reactive.",
    )
    if request.headers.get("HX-Request") == "true":
        return _render_it_action_panel(request)
    return _redirect_it_dashboard(request)


@_position_required({"it_support"})
def it_unblock_account(request):
    if request.method != "POST":
        return _deny_portal_access(request)

    branch, target_user = _get_manageable_target_user(request)
    if target_user is None:
        _store_it_support_feedback(
            request,
            level="error",
            title="Action refusee",
            message="Le compte cible est introuvable ou hors du perimetre de cette annexe.",
        )
        return _redirect_it_dashboard(request)

    unblock_account(actor=request.user, branch=branch, target_user=target_user)
    _store_it_support_feedback(
        request,
        level="success",
        title="Compte debloque",
        message=f"Les blocages du compte {target_user.get_full_name() or target_user.username} ont ete leves.",
    )
    if request.headers.get("HX-Request") == "true":
        return _render_it_action_panel(request)
    return _redirect_it_dashboard(request)


@_position_required({"it_support"})
def it_update_account_email(request):
    if request.method != "POST":
        return _deny_portal_access(request)

    branch, target_user = _get_manageable_target_user(request)
    if target_user is None:
        _store_it_support_feedback(
            request,
            level="error",
            title="Action refusee",
            message="Le compte cible est introuvable ou hors du perimetre de cette annexe.",
        )
        return _redirect_it_dashboard(request)
    email = (request.POST.get("email") or "").strip()
    try:
        validate_email(email)
    except ValidationError:
        _store_it_support_feedback(
            request,
            level="error",
            title="Email invalide",
            message="Adresse email non valide.",
        )
        if request.headers.get("HX-Request") == "true":
            return _render_it_action_panel(request)
        return _redirect_it_dashboard(request)

    update_account_email(actor=request.user, branch=branch, target_user=target_user, email=email)
    _store_it_support_feedback(
        request,
        level="success",
        title="Email corrige",
        message=f"Le nouvel email du compte est {target_user.email}.",
    )
    if request.headers.get("HX-Request") == "true":
        return _render_it_action_panel(request)
    return _redirect_it_dashboard(request)


@_position_required({"it_support"})
def it_diagnostics_panel(request):
    context = _build_it_dashboard_context(request)
    return render(request, "portal/informaticien/partials/diagnostics_panel.html", context)


@_position_required({"it_support"})
def it_accounts_panel(request):
    context = _build_it_dashboard_context(request)
    return render(request, "portal/informaticien/partials/accounts_panel.html", context)


def _build_it_support_panel_context(request):
    branch = _resolve_academic_branch(request)
    status = (request.GET.get("status") or "").strip()
    context = _build_it_dashboard_context(request)
    context.update(
        {
            "ticket_status_filter": status,
            "ticket_status_choices": SupportTicket.STATUS_CHOICES,
            "ticket_category_choices": SupportTicket.CATEGORY_CHOICES,
            "ticket_priority_choices": SupportTicket.PRIORITY_CHOICES,
            "support_ticket_metrics": get_support_ticket_metrics(branch=branch),
            "support_tickets": list(get_support_ticket_queryset(branch=branch, status=status)[:12]),
        }
    )
    return context


@_position_required({"it_support"})
def it_support_panel(request):
    return render(
        request,
        "portal/informaticien/partials/support_panel.html",
        _build_it_support_panel_context(request),
    )


@_position_required({"it_support"})
def it_create_ticket(request):
    if request.method != "POST":
        return _deny_portal_access(request)
    branch = _resolve_academic_branch(request)
    requester_user = None
    student = None
    inscription = None
    kind = (request.POST.get("kind") or "").strip()
    object_id = (request.POST.get("object_id") or "").strip()
    if object_id.isdigit():
        diagnostic = build_diagnostic_payload(branch=branch, kind=kind, object_id=int(object_id))
        if diagnostic:
            if diagnostic.get("target_user_id"):
                requester_user = request.user.__class__.objects.filter(pk=diagnostic["target_user_id"]).first()
            if kind == "student":
                student = Student.objects.filter(pk=int(object_id)).first()
                inscription = student.inscription if student else None
            elif kind == "inscription":
                inscription = Inscription.objects.filter(pk=int(object_id)).first()
                student = getattr(inscription, "student", None) if inscription else None
    try:
        create_support_ticket(
            actor=request.user,
            branch=branch,
            title=request.POST.get("title"),
            description=request.POST.get("description"),
            category=request.POST.get("category"),
            priority=request.POST.get("priority"),
            requester_user=requester_user,
            student=student,
            inscription=inscription,
        )
    except ValueError as exc:
        context = _build_it_support_panel_context(request)
        context["ticket_feedback"] = {"level": "error", "message": str(exc)}
        return render(request, "portal/informaticien/partials/support_panel.html", context)
    context = _build_it_support_panel_context(request)
    context["ticket_feedback"] = {"level": "success", "message": "Ticket cree et ajoute a la file support."}
    return render(request, "portal/informaticien/partials/support_panel.html", context)


def _get_scoped_ticket_or_none(*, request, ticket_id):
    branch = _resolve_academic_branch(request)
    ticket = get_support_ticket_queryset(branch=branch).filter(pk=ticket_id).first()
    return branch, ticket


@_position_required({"it_support"})
def it_assign_ticket(request, ticket_id):
    if request.method != "POST":
        return _deny_portal_access(request)
    branch, ticket = _get_scoped_ticket_or_none(request=request, ticket_id=ticket_id)
    if not ticket:
        return _deny_portal_access(request)
    assign_support_ticket(actor=request.user, branch=branch, ticket=ticket)
    return render(request, "portal/informaticien/partials/support_panel.html", _build_it_support_panel_context(request))


@_position_required({"it_support"})
def it_update_ticket_status(request, ticket_id):
    if request.method != "POST":
        return _deny_portal_access(request)
    branch, ticket = _get_scoped_ticket_or_none(request=request, ticket_id=ticket_id)
    if not ticket:
        return _deny_portal_access(request)
    try:
        update_support_ticket_status(
            actor=request.user,
            branch=branch,
            ticket=ticket,
            status=request.POST.get("status"),
            resolution=request.POST.get("resolution"),
        )
    except ValueError as exc:
        context = _build_it_support_panel_context(request)
        context["ticket_feedback"] = {"level": "error", "message": str(exc)}
        return render(request, "portal/informaticien/partials/support_panel.html", context)
    return render(request, "portal/informaticien/partials/support_panel.html", _build_it_support_panel_context(request))


@_position_required({"it_support"})
def it_comment_ticket(request, ticket_id):
    if request.method != "POST":
        return _deny_portal_access(request)
    branch, ticket = _get_scoped_ticket_or_none(request=request, ticket_id=ticket_id)
    if not ticket:
        return _deny_portal_access(request)
    try:
        add_support_ticket_comment(
            actor=request.user,
            branch=branch,
            ticket=ticket,
            body=request.POST.get("body"),
        )
    except ValueError as exc:
        context = _build_it_support_panel_context(request)
        context["ticket_feedback"] = {"level": "error", "message": str(exc)}
        return render(request, "portal/informaticien/partials/support_panel.html", context)
    return render(request, "portal/informaticien/partials/support_panel.html", _build_it_support_panel_context(request))


def _parse_slot_time_hhmm(raw: str):
    value = (raw or "").strip()
    if not value:
        raise ValidationError("Heure obligatoire.")
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    raise ValidationError("Format d'heure attendu : HH:MM.")


def _build_weekly_slots_workspace_context(
    request,
    *,
    branch,
    class_id: int,
    week_start,
    editing_slot_id=None,
    toast=None,
):
    ctx = build_class_detail_context(
        request,
        branch=branch,
        class_id=class_id,
        week_start=week_start,
    )
    academic_class = ctx["academic_class"]
    slots = list_weekly_slots_for_class(academic_class)
    ctx["weekly_slot_rows"] = [serialize_weekly_slot_for_ui(s) for s in slots]
    ctx["weekday_choices"] = WeeklyScheduleSlot.WEEKDAY_CHOICES
    ctx["editing_slot"] = None
    if editing_slot_id:
        slot = (
            WeeklyScheduleSlot.objects.select_related("ec", "teacher")
            .filter(
                pk=editing_slot_id,
                academic_class=academic_class,
                branch=branch,
                is_active=True,
            )
            .first()
        )
        if slot:
            ctx["editing_slot"] = serialize_weekly_slot_for_ui(slot)
    if toast is not None:
        ctx["toast"] = toast
    return ctx


def _inject_planner_route_context(context, *, role_prefix: str, workspace_target_id: str):
    context.update(
        {
            "workspace_target_id": workspace_target_id,
            "planner_hub_url": f"accounts_portal:{role_prefix}_planner_hub",
            "planner_view_url": f"accounts_portal:{role_prefix}_planner_view_workspace",
            "planner_workspace_url": f"accounts_portal:{role_prefix}_planner_workspace",
            "weekly_slots_workspace_url": f"accounts_portal:{role_prefix}_weekly_slots_workspace",
            "weekly_slot_save_url": f"accounts_portal:{role_prefix}_weekly_slot_save",
            "week_materialize_url": f"accounts_portal:{role_prefix}_week_materialize",
            "month_materialize_url": f"accounts_portal:{role_prefix}_month_materialize",
            "create_schedule_event_url": f"accounts_portal:{role_prefix}_create_schedule_event",
            "class_print_url": "accounts_portal:schedule_class_print",
            "teacher_print_url": "accounts_portal:schedule_teacher_print",
        }
    )
    return context


def _materialize_period_from_weekly_slots(*, user, academic_class, week_start, weeks_count: int):
    from academics.services.schedule_service import materialize_week_events_from_weekly_slots

    created = 0
    skipped = 0
    normalized_week = week_start
    for offset in range(max(1, weeks_count)):
        cursor = normalized_week + timedelta(days=7 * offset)
        result = materialize_week_events_from_weekly_slots(
            user=user,
            academic_class=academic_class,
            week_start=cursor,
        )
        created += result["created"]
        skipped += result["skipped_existing"]
    return {"created": created, "skipped_existing": skipped, "weeks_count": max(1, weeks_count)}


def _parse_planning_period_request(request):
    week_start_raw = (request.GET.get("week_start") or "").strip()
    week_start = timezone.localdate()
    if week_start_raw:
        try:
            week_start = datetime.strptime(week_start_raw, "%Y-%m-%d").date()
        except ValueError:
            week_start = timezone.localdate()
    period = (request.GET.get("period") or "week").strip().lower()
    if period not in {"week", "month"}:
        period = "week"
    normalized_week = week_start - timedelta(days=week_start.weekday())
    weeks = 4 if period == "month" else 1
    return normalized_week, period, weeks


def _build_print_week_blocks(schedule_builder, target, week_start, weeks):
    blocks = []
    for offset in range(weeks):
        cursor = week_start + timedelta(days=7 * offset)
        blocks.append(schedule_builder(target, cursor))
    return blocks


def _parse_director_planner_request(request):
    branch = _resolve_director_branch(request)
    class_id_raw = (request.GET.get("class_id") or request.POST.get("class_id") or "").strip()
    week_start_raw = (request.GET.get("week_start") or request.POST.get("week_start") or "").strip()
    week_start = timezone.localdate()
    if week_start_raw:
        try:
            week_start = datetime.strptime(week_start_raw, "%Y-%m-%d").date()
        except ValueError:
            week_start = timezone.localdate()
    class_id = int(class_id_raw) if class_id_raw.isdigit() else None
    return branch, class_id, week_start


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_planner_hub(request):
    branch, class_id, week_start = _parse_director_planner_request(request)
    if branch is None:
        return render(request, "portal/staff/supervisor/partials/planner_class_hub.html", {"academic_class": None, "toast": {"level": "error", "message": "Aucune annexe n'est rattachee a ce compte."}})
    if class_id is None:
        return render(request, "portal/staff/supervisor/partials/planner_class_hub.html", {"branch": branch, "academic_class": None})
    context = build_class_detail_context(request, branch=branch, class_id=class_id, week_start=week_start)
    _inject_planner_route_context(context, role_prefix="director", workspace_target_id="#director-workspace")
    return render(request, "portal/staff/supervisor/partials/planner_class_hub.html", context)


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_planner_view_workspace(request):
    branch, class_id, week_start = _parse_director_planner_request(request)
    if branch is None:
        return render(request, "portal/staff/supervisor/partials/planner_view_workspace.html", {"academic_class": None, "toast": {"level": "error", "message": "Aucune annexe n'est rattachee a ce compte."}})
    if class_id is None:
        return render(request, "portal/staff/supervisor/partials/planner_view_workspace.html", {"branch": branch, "academic_class": None})
    context = build_class_detail_context(request, branch=branch, class_id=class_id, week_start=week_start)
    _inject_planner_route_context(context, role_prefix="director", workspace_target_id="#director-workspace")
    return render(request, "portal/staff/supervisor/partials/planner_view_workspace.html", context)


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_planner_workspace(request):
    branch, class_id, week_start = _parse_director_planner_request(request)
    if branch is None:
        return render(request, "portal/staff/supervisor/partials/planner_workspace.html", {"academic_class": None, "toast": {"level": "error", "message": "Aucune annexe n'est rattachee a ce compte."}})
    if class_id is None:
        return render(request, "portal/staff/supervisor/partials/planner_workspace.html", {"branch": branch, "academic_class": None})
    context = build_class_detail_context(request, branch=branch, class_id=class_id, week_start=week_start)
    context["planner_intent"] = (request.GET.get("intent") or "create").strip() or "create"
    _inject_planner_route_context(context, role_prefix="director", workspace_target_id="#director-workspace")
    return render(request, "portal/staff/supervisor/partials/planner_workspace.html", context)


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_weekly_slots_workspace(request, class_id: int):
    branch = _resolve_director_branch(request)
    _DE_SLOTS_TPL = "portal/staff/director/partials/director_weekly_slots_workspace.html"
    _DE_FORM_TPL = "portal/staff/director/partials/director_weekly_slot_form_drawer.html"
    if branch is None:
        return render(request, _DE_SLOTS_TPL, {"academic_class": None, "toast": {"level": "error", "message": "Aucune annexe n'est rattachee a ce compte."}})
    week_start_raw = (request.GET.get("week_start") or "").strip()
    week_start = timezone.localdate()
    if week_start_raw:
        try:
            week_start = datetime.strptime(week_start_raw, "%Y-%m-%d").date()
        except ValueError:
            week_start = timezone.localdate()
    edit_raw = (request.GET.get("edit") or "").strip()
    editing_slot_id = int(edit_raw) if edit_raw.isdigit() else None
    drawer_form = request.GET.get("drawer_form") == "1"
    try:
        context = _build_weekly_slots_workspace_context(request, branch=branch, class_id=class_id, week_start=week_start, editing_slot_id=editing_slot_id)
    except AcademicClass.DoesNotExist:
        return render(request, _DE_SLOTS_TPL, {"academic_class": None, "toast": {"level": "error", "message": "Classe introuvable pour cette annexe."}})
    _inject_planner_route_context(context, role_prefix="director", workspace_target_id="#director-workspace")
    return render(request, _DE_FORM_TPL if drawer_form else _DE_SLOTS_TPL, context)


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_weekly_slot_save(request, class_id: int):
    if request.method != "POST":
        return _deny_portal_access(request)

    branch = _resolve_director_branch(request)
    if branch is None:
        return render(
            request,
            "portal/staff/director/partials/director_weekly_slots_workspace.html",
            {"toast": {"level": "error", "message": "Aucune annexe n'est rattachee a ce compte."}, "academic_class": None},
        )

    week_start_raw = (request.POST.get("week_start") or "").strip()
    week_start = timezone.localdate()
    if week_start_raw:
        try:
            week_start = datetime.strptime(week_start_raw, "%Y-%m-%d").date()
        except ValueError:
            week_start = timezone.localdate()

    action = (request.POST.get("action") or "create").strip().lower()
    toast = None

    from django.contrib.auth import get_user_model

    User = get_user_model()

    try:
        academic_class = AcademicClass.objects.select_related("academic_year", "branch").get(pk=class_id, branch=branch, is_active=True)

        if action == "delete":
            slot_raw = (request.POST.get("slot_id") or "").strip()
            if not slot_raw.isdigit():
                raise ValidationError("Creneau invalide.")
            slot = WeeklyScheduleSlot.objects.get(pk=int(slot_raw), academic_class=academic_class, branch=branch)
            deactivate_weekly_schedule_slot(slot)
            toast = {"level": "success", "message": "Creneau retire de la grille hebdomadaire."}
        elif action in {"update", "create"}:
            ec = EC.objects.select_related("ue", "ue__semester").get(pk=request.POST.get("ec_id"), ue__semester__academic_class=academic_class)
            teacher = User.objects.get(pk=request.POST.get("teacher_id"), is_active=True)
            weekday_raw = (request.POST.get("weekday") or "").strip()
            if not weekday_raw.isdigit():
                raise ValidationError("Jour de semaine invalide.")
            weekday = int(weekday_raw)
            if weekday < 0 or weekday > 6:
                raise ValidationError("Jour de semaine hors plage (0-6).")
            start_t = _parse_slot_time_hhmm(request.POST.get("start_time"))
            end_t = _parse_slot_time_hhmm(request.POST.get("end_time"))
            if end_t <= start_t:
                raise ValidationError("L'heure de fin doit etre apres l'heure de debut.")
            room = (request.POST.get("room") or "").strip()

            if action == "update":
                slot_raw = (request.POST.get("slot_id") or "").strip()
                if not slot_raw.isdigit():
                    raise ValidationError("Creneau invalide.")
                slot = WeeklyScheduleSlot.objects.get(pk=int(slot_raw), academic_class=academic_class, branch=branch, is_active=True)
                update_weekly_schedule_slot(slot, weekday=weekday, ec=ec, teacher=teacher, start_time=start_t, end_time=end_t, room=room, is_active=True)
                toast = {"level": "success", "message": "Creneau hebdomadaire mis a jour."}
            else:
                create_weekly_schedule_slot(
                    user=request.user,
                    academic_class=academic_class,
                    ec=ec,
                    teacher=teacher,
                    branch=branch,
                    academic_year=academic_class.academic_year,
                    weekday=weekday,
                    start_time=start_t,
                    end_time=end_t,
                    room=room,
                    is_active=True,
                )
                toast = {"level": "success", "message": "Creneau hebdomadaire cree."}
        else:
            raise ValidationError("Action non reconnue.")
    except (AcademicClass.DoesNotExist, WeeklyScheduleSlot.DoesNotExist, EC.DoesNotExist, User.DoesNotExist):
        toast = {"level": "error", "message": "Donnee introuvable ou hors du perimetre de cette classe."}
    except ValidationError as exc:
        toast = {"level": "error", "message": " ".join(exc.messages)}

    context = _build_weekly_slots_workspace_context(
        request,
        branch=branch,
        class_id=class_id,
        week_start=week_start,
        editing_slot_id=None,
        toast=toast,
    )
    _inject_planner_route_context(context, role_prefix="director", workspace_target_id="#director-workspace")
    return render(request, "portal/staff/director/partials/director_weekly_slots_workspace.html", context)


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_week_materialize(request, class_id: int):
    if request.method != "POST":
        return _deny_portal_access(request)
    branch = _resolve_director_branch(request)
    if branch is None:
        return render(request, "portal/staff/director/partials/director_weekly_slots_workspace.html", {"academic_class": None, "toast": {"level": "error", "message": "Aucune annexe n'est rattachee a ce compte."}})
    week_start_raw = (request.POST.get("week_start") or "").strip()
    week_start = timezone.localdate()
    if week_start_raw:
        try:
            week_start = datetime.strptime(week_start_raw, "%Y-%m-%d").date()
        except ValueError:
            week_start = timezone.localdate()
    try:
        academic_class = AcademicClass.objects.select_related("academic_year", "branch").get(pk=class_id, branch=branch, is_active=True)
        result = _materialize_period_from_weekly_slots(user=request.user, academic_class=academic_class, week_start=week_start, weeks_count=1)
        toast = {"level": "success", "message": f"Semaine generee: {result['created']} cours crees ({result['skipped_existing']} deja presents)."}
    except AcademicClass.DoesNotExist:
        toast = {"level": "error", "message": "Classe introuvable pour cette annexe."}
    context = _build_weekly_slots_workspace_context(request, branch=branch, class_id=class_id, week_start=week_start, editing_slot_id=None, toast=toast)
    _inject_planner_route_context(context, role_prefix="director", workspace_target_id="#director-workspace")
    return render(request, "portal/staff/director/partials/director_weekly_slots_workspace.html", context)


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_month_materialize(request, class_id: int):
    if request.method != "POST":
        return _deny_portal_access(request)
    branch = _resolve_director_branch(request)
    if branch is None:
        return render(request, "portal/staff/director/partials/director_weekly_slots_workspace.html", {"academic_class": None, "toast": {"level": "error", "message": "Aucune annexe n'est rattachee a ce compte."}})
    week_start_raw = (request.POST.get("week_start") or "").strip()
    week_start = timezone.localdate()
    if week_start_raw:
        try:
            week_start = datetime.strptime(week_start_raw, "%Y-%m-%d").date()
        except ValueError:
            week_start = timezone.localdate()
    try:
        academic_class = AcademicClass.objects.select_related("academic_year", "branch").get(pk=class_id, branch=branch, is_active=True)
        result = _materialize_period_from_weekly_slots(user=request.user, academic_class=academic_class, week_start=week_start, weeks_count=4)
        toast = {"level": "success", "message": f"Mois pedagogique genere: {result['created']} cours crees ({result['skipped_existing']} deja presents)."}
    except AcademicClass.DoesNotExist:
        toast = {"level": "error", "message": "Classe introuvable pour cette annexe."}
    context = _build_weekly_slots_workspace_context(request, branch=branch, class_id=class_id, week_start=week_start, editing_slot_id=None, toast=toast)
    _inject_planner_route_context(context, role_prefix="director", workspace_target_id="#director-workspace")
    return render(request, "portal/staff/director/partials/director_weekly_slots_workspace.html", context)


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_create_schedule_event(request, class_id: int):
    if request.method != "POST":
        return _deny_portal_access(request)

    branch = _resolve_director_branch(request)
    if branch is None:
        return _deny_portal_access(request)

    from django.contrib.auth import get_user_model

    from academics.models import AcademicClass, AcademicScheduleEvent, EC
    from academics.services.schedule_service import create_schedule_event

    User = get_user_model()
    academic_class = AcademicClass.objects.select_related("academic_year", "branch").filter(pk=class_id, branch=branch, is_active=True).first()
    if academic_class is None:
        return HttpResponseForbidden("Classe introuvable pour cette annexe.")

    ec = EC.objects.select_related("ue", "ue__semester").filter(
        pk=request.POST.get("ec_id"),
        ue__semester__academic_class=academic_class,
    ).first()
    if ec is None:
        return HttpResponseForbidden("Matiere introuvable pour cette annexe.")

    teacher = User.objects.select_related("profile", "profile__branch").filter(
        pk=request.POST.get("teacher_id"),
        is_active=True,
        profile__branch=branch,
        profile__position="teacher",
    ).first()
    if teacher is None:
        return HttpResponseForbidden("Enseignant introuvable pour cette annexe.")
    date_value = (request.POST.get("date") or "").strip()
    start_time = (request.POST.get("start_time") or "").strip()
    end_time = (request.POST.get("end_time") or "").strip()
    location = (request.POST.get("location") or "").strip()
    is_online = bool((request.POST.get("is_online") or "").strip())

    try:
        if not (date_value and start_time and end_time):
            raise ValidationError("Date, heure debut et heure fin sont obligatoires.")
        start_dt = timezone.make_aware(datetime.strptime(f"{date_value} {start_time}", "%Y-%m-%d %H:%M"))
        end_dt = timezone.make_aware(datetime.strptime(f"{date_value} {end_time}", "%Y-%m-%d %H:%M"))
        if end_dt <= start_dt:
            raise ValidationError("L'heure de fin doit etre apres l'heure de debut.")

        create_schedule_event(
            user=request.user,
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            status=AcademicScheduleEvent.STATUS_PLANNED,
            academic_class=academic_class,
            academic_year=academic_class.academic_year,
            branch=branch,
            ec=ec,
            teacher=teacher,
            title=f"{ec.title} - {academic_class.display_name}",
            description="",
            start_datetime=start_dt,
            end_datetime=end_dt,
            location=location,
            is_online=is_online,
            is_active=True,
        )
        toast = {"level": "success", "message": "Cours programme sur la semaine."}
    except ValidationError as exc:
        msg = " ".join(getattr(exc, "messages", [])) if hasattr(exc, "messages") else str(exc)
        toast = {"level": "error", "message": msg or "Impossible de programmer ce cours."}

    week_start_raw = (request.POST.get("week_start") or "").strip()
    week_start = timezone.localdate()
    if week_start_raw:
        try:
            week_start = datetime.strptime(week_start_raw, "%Y-%m-%d").date()
        except ValueError:
            week_start = timezone.localdate()
    context = build_class_detail_context(request, branch=branch, class_id=class_id, week_start=week_start)
    context["toast"] = toast
    context["planner_intent"] = (request.POST.get("planner_intent") or "create").strip() or "create"
    _inject_planner_route_context(context, role_prefix="director", workspace_target_id="#director-workspace")
    return render(request, "portal/staff/supervisor/partials/planner_workspace.html", context)


@_position_required({"director_of_studies", "academic_supervisor", "executive_director", "deputy_executive_director", "super_admin"})
def schedule_class_print(request, class_id: int):
    branch = _resolve_director_branch(
        request,
        additional_scoped_positions={"academic_supervisor"},
    )
    if branch is None:
        return HttpResponseForbidden("Aucune annexe n'est rattachee a ce compte.")

    academic_class = AcademicClass.objects.select_related("programme", "academic_year", "branch").filter(
        pk=class_id,
        branch=branch,
        is_active=True,
    ).first()
    if academic_class is None:
        return HttpResponseForbidden("Classe introuvable pour cette annexe.")

    if (request.GET.get("source") or "").strip().lower() == "weekly":
        week_start = _parse_director_week_start(request)
        return render(
            request,
            "portal/staff/shared/prints/class_schedule_print.html",
            {
                "branch": branch,
                "academic_class": academic_class,
                "weekly_grid": build_weekly_timetable_grid(
                    academic_class, week_start=week_start
                ),
                "source": "weekly",
                "generated_at": timezone.now(),
            },
        )

    week_start, period, weeks = _parse_planning_period_request(request)
    week_blocks = _build_print_week_blocks(get_class_week_schedule, academic_class, week_start, weeks)
    return render(
        request,
        "portal/staff/shared/prints/class_schedule_print.html",
        {
            "branch": branch,
            "academic_class": academic_class,
            "week_blocks": week_blocks,
            "period": period,
            "generated_at": timezone.now(),
        },
    )


@_position_required({"director_of_studies", "academic_supervisor", "executive_director", "deputy_executive_director", "super_admin"})
def schedule_teacher_print(request, teacher_id: int):
    branch = _resolve_director_branch(
        request,
        additional_scoped_positions={"academic_supervisor"},
    )
    if branch is None:
        return HttpResponseForbidden("Aucune annexe n'est rattachee a ce compte.")

    teacher = get_user_model().objects.select_related("profile").filter(
        pk=teacher_id,
        is_active=True,
        profile__branch=branch,
        profile__position="teacher",
    ).first()
    if teacher is None:
        return HttpResponseForbidden("Enseignant introuvable pour cette annexe.")

    week_start, period, weeks = _parse_planning_period_request(request)
    week_blocks = _build_print_week_blocks(get_teacher_week_schedule, teacher, week_start, weeks)
    return render(
        request,
        "portal/staff/shared/prints/teacher_schedule_print.html",
        {
            "branch": branch,
            "teacher": teacher,
            "week_blocks": week_blocks,
            "period": period,
            "generated_at": timezone.now(),
        },
    )

@login_required
def dg_portal(request):
    position = get_user_position(request.user)
    if position not in {"executive_director", "deputy_executive_director"}:
        return HttpResponseForbidden("Accès réservé au Directeur Général.")
    context = build_dg_dashboard_context(request, _build_portal_context)
    active_section = (request.GET.get("section") or "overview").strip().lower()
    allowed_sections = {
        "overview", "alerts", "workflows", "schedule", "annexes", "finance",
        "coupons", "rh", "analytics", "realtime",
    }
    if active_section not in allowed_sections:
        active_section = "overview"
    dashboard_url = reverse("accounts_portal:portal_dg")
    context.update(
        build_role_dashboard_shell(
            request,
            role=position,
            key="executive",
            title="Direction générale",
            subtitle="Pilotage institutionnel",
            active_section=active_section,
            dashboard_url=dashboard_url,
            context_label=context.get("dashboard_scope_label") or "Toutes les annexes",
            groups=[
                {
                    "label": "Pilotage",
                    "items": [
                        {"key": "overview", "label": "Vue globale", "icon": "layout-dashboard", "url": f"{dashboard_url}#overview"},
                        {"key": "analytics", "label": "Analytics", "icon": "chart-no-axes-combined", "url": f"{dashboard_url}#analytics"},
                        {"key": "realtime", "label": "Temps réel", "icon": "activity", "url": f"{dashboard_url}#realtime"},
                    ],
                },
                {
                    "label": "Opérations",
                    "items": [
                        {"key": "alerts", "label": "Alertes et risques", "icon": "triangle-alert", "url": f"{dashboard_url}#alerts", "badge": context.get("open_alerts") or None},
                        {"key": "workflows", "label": "Passages et réinscriptions", "icon": "refresh-cw", "url": f"{dashboard_url}#workflows", "badge": (context.get("workflow") or {}).get("blocked_count") or None},
                        {"key": "schedule", "label": "Emploi du temps", "icon": "calendar-days", "url": f"{dashboard_url}#schedule"},
                    ],
                },
                {
                    "label": "Ressources",
                    "items": [
                        {"key": "annexes", "label": "Annexes", "icon": "building-2", "url": f"{dashboard_url}#annexes"},
                        {"key": "rh", "label": "RH / Staff", "icon": "users", "url": f"{dashboard_url}#rh"},
                        {"key": "finance", "label": "Finance", "icon": "hand-coins", "url": f"{dashboard_url}#finance"},
                        {"key": "coupons", "label": "Coupons", "icon": "ticket-percent", "url": f"{dashboard_url}#coupons"},
                    ],
                },
            ],
            topbar_template="portal/dg/partials/topbar_actions.html",
            drawer_title="Détail exécutif",
            modal_title="Décision exécutive",
        )
    )
    return render(request, "portal/dg/dashboard.html", context)


@login_required
def dg_section(request, section: str):
    position = get_user_position(request.user)
    if position not in {"executive_director", "deputy_executive_director"}:
        return HttpResponseForbidden("Accès réservé au Directeur Général.")
    context = build_dg_section_context(request, section, _build_portal_context)
    if section == "workflows":
        terminal_classes = AcademicClass.objects.select_related("branch", "academic_year", "programme").filter(
            is_active=True,
            level__in=["L3", "M2"],
        )
        diploma_rows = []
        for academic_class in terminal_classes[:30]:
            semesters = list(academic_class.semesters.all())
            if not semesters:
                continue
            published_count = sum(1 for semester in semesters if semester.status == Semester.STATUS_PUBLISHED)
            if published_count < len(semesters):
                continue
            student_count = academic_class.enrollments.filter(is_active=True).count()
            awards_count = AcademicDiplomaAward.objects.filter(academic_class=academic_class).exclude(
                status=AcademicDiplomaAward.STATUS_CANCELLED
            ).count()
            diploma_rows.append(
                {
                    "class": academic_class,
                    "student_count": student_count,
                    "published_count": published_count,
                    "semester_count": len(semesters),
                    "awards_count": awards_count,
                }
            )
        context["diploma_candidate_classes"] = diploma_rows
    if section == "coupons":
        context.update(_build_coupons_section_extra_context())
    template_map = {
        "kpis": "portal/dg/partials/kpis/overview.html",
        "alerts": "portal/dg/partials/alerts/priority_table.html",
        "workflows": "portal/dg/partials/workflows/reenrollment.html",
        "finance": "portal/dg/partials/finance/summary.html",
        "annexes": "portal/dg/partials/annexes/performance_table.html",
        "analytics": "portal/dg/partials/analytics/charts.html",
        "schedule": "portal/dg/partials/schedule/overview.html",
        "realtime": "portal/dg/partials/realtime/monitoring.html",
        "rh": "portal/dg/partials/rh/staff.html",
        "coupons": "portal/dg/partials/coupons/list.html",
    }
    template = template_map.get(section)
    if not template:
        return HttpResponseBadRequest("Section DG inconnue.")
    return render(request, template, context)


@login_required
def dg_drawer(request):
    position = get_user_position(request.user)
    if position not in {"executive_director", "deputy_executive_director"}:
        return HttpResponseForbidden("Accès réservé au Directeur Général.")
    return render(request, "portal/dg/drawers/detail.html", build_dg_drawer_context(request))


@login_required
def dg_modal(request):
    position = get_user_position(request.user)
    if position not in {"executive_director", "deputy_executive_director"}:
        return HttpResponseForbidden("Accès réservé au Directeur Général.")
    modal = (request.GET.get("modal") or "recruitment").strip().lower()
    if modal == "recruitment":
        return render(request, "portal/dg/modals/recruitment.html", {"form": DgRecruitmentForm()})
    if modal == "coupon":
        return render(request, "portal/dg/modals/coupon_form.html", {"form": DgCouponForm()})
    if modal == "coupon_detail":
        coupon_id = (request.GET.get("coupon_id") or "").strip()
        if not coupon_id.isdigit():
            return HttpResponseBadRequest("Coupon invalide.")
        coupon = get_coupon_detail(int(coupon_id))
        if coupon is None:
            return HttpResponse("Coupon introuvable.", status=404)
        return render(request, "portal/dg/modals/coupon_detail.html", {"coupon": coupon})
    if modal in {"branch", "alert", "case", "workflow", "finance", "analytics", "realtime", "rh"}:
        context = build_dg_drawer_context(request)
        context.update(
            {
                "modal_kind": modal,
                "modal_title": {
                    "branch": "Fiche annexe detaillee",
                    "alert": "Alerte detaillee",
                    "case": "Dossier etudiant detaille",
                    "workflow": "Workflow detaille",
                    "finance": "Synthese financiere detaillee",
                    "analytics": "Lecture analytique detaillee",
                    "realtime": "Vue live detaillee",
                    "rh": "Lecture RH detaillee",
                }[modal],
                "modal_finance": context.get("drawer_branch_finance") or context.get("drawer_finance") or context.get("finance"),
            }
        )
        return render(request, "portal/dg/modals/detail.html", context)
    return HttpResponseBadRequest("Modal DG inconnue.")


@login_required
def dg_recruit_staff(request):
    position = get_user_position(request.user)
    if position not in {"executive_director", "deputy_executive_director"}:
        return HttpResponseForbidden("Accès réservé au Directeur Général.")
    if request.method != "POST":
        return HttpResponseBadRequest("Methode invalide.")
    form = DgRecruitmentForm(request.POST)
    if not form.is_valid():
        return render(request, "portal/dg/modals/recruitment.html", {"form": form}, status=400)
    result = create_staff_from_recruitment(actor=request.user, form=form)
    return render(request, "portal/dg/modals/recruitment_success.html", result)


def _build_coupons_section_extra_context():
    coupons = list(list_coupons())
    return {
        "coupons": coupons,
        "coupon_form": DgCouponForm(),
        "coupon_stats": {
            "total": len(coupons),
            "available": sum(coupon.is_currently_valid() for coupon in coupons),
            "uses": sum(coupon.usage_count for coupon in coupons),
            "discount_total": sum((coupon.discount_total or 0) for coupon in coupons),
        },
    }


@login_required
@require_GET
def dg_coupon_programmes_options(request):
    position = get_user_position(request.user)
    if position not in {"executive_director", "deputy_executive_director"}:
        return HttpResponseForbidden("Accès réservé au Directeur Général.")
    branch_ids = request.GET.getlist("branches")
    programmes = DgCouponForm.programmes_queryset_for_branches(branch_ids)
    return render(
        request,
        "portal/dg/modals/coupon_programmes_options.html",
        {"programmes": programmes},
    )


@login_required
@require_POST
def dg_coupon_create(request):
    position = get_user_position(request.user)
    if position not in {"executive_director", "deputy_executive_director"}:
        return HttpResponseForbidden("Accès réservé au Directeur Général.")
    form = DgCouponForm(request.POST)
    if not form.is_valid():
        return render(request, "portal/dg/modals/coupon_form.html", {"form": form}, status=400)
    try:
        coupon = create_coupon(actor=request.user, form=form)
    except ValidationError as exc:
        for field, messages in getattr(exc, "message_dict", {"__all__": exc.messages}).items():
            for message in messages:
                form.add_error(field if field in form.fields else None, message)
        return render(request, "portal/dg/modals/coupon_form.html", {"form": form}, status=400)
    return render(request, "portal/dg/modals/coupon_success.html", {"coupon": coupon})


@login_required
@require_POST
def dg_coupon_toggle(request):
    position = get_user_position(request.user)
    if position not in {"executive_director", "deputy_executive_director"}:
        return HttpResponseForbidden("Accès réservé au Directeur Général.")
    coupon_id = (request.POST.get("coupon_id") or "").strip()
    if not coupon_id.isdigit():
        return HttpResponseBadRequest("Coupon invalide.")
    coupon = toggle_coupon(actor=request.user, coupon_id=int(coupon_id))
    if coupon is None:
        return HttpResponse("Coupon introuvable.", status=404)
    context = build_dg_section_context(request, "coupons", _build_portal_context)
    context.update(_build_coupons_section_extra_context())
    return render(request, "portal/dg/partials/coupons/list.html", context)


@login_required
def dg_action(request):
    position = get_user_position(request.user)
    if position not in {"executive_director", "deputy_executive_director"}:
        return HttpResponseForbidden("Acces reserve au Directeur General.")
    if request.method != "POST":
        return HttpResponseBadRequest("Methode invalide.")

    action = (request.POST.get("action") or "").strip()
    object_id = (request.POST.get("object_id") or "").strip()
    if action not in {"resolve_alert", "resolve_case", "escalate_case", "followup_finance"}:
        return JsonResponse({"ok": False, "message": "Action DG inconnue."}, status=400)
    if not object_id.isdigit():
        return JsonResponse({"ok": False, "message": "Reference invalide."}, status=400)

    try:
        if action == "resolve_alert":
            result = resolve_attendance_alert(actor=request.user, alert_id=int(object_id))
        elif action == "resolve_case":
            result = resolve_student_case(actor=request.user, case_id=int(object_id))
        elif action == "escalate_case":
            result = escalate_student_case(actor=request.user, case_id=int(object_id))
        else:
            branch = Branch.objects.get(id=int(object_id), is_active=True)
            result = create_finance_followup(actor=request.user, branch=branch)
    except (AttendanceAlert.DoesNotExist, StudentCase.DoesNotExist, Branch.DoesNotExist):
        return JsonResponse({"ok": False, "message": "Element introuvable."}, status=404)
    return JsonResponse({"ok": True, **result})


@login_required
def dg_diploma_action(request):
    position = get_user_position(request.user)
    if position not in {"executive_director", "deputy_executive_director"}:
        return HttpResponseForbidden("Acces reserve a la Direction Generale.")
    if request.method != "POST":
        return HttpResponseBadRequest("Methode invalide.")
    class_id = (request.POST.get("class_id") or "").strip()
    publish = (request.POST.get("publish") or "").strip().lower() in {"1", "true", "yes", "on"}
    if not class_id.isdigit():
        return JsonResponse({"ok": False, "message": "Classe invalide."}, status=400)
    try:
        academic_class = AcademicClass.objects.select_related("branch", "academic_year", "programme").get(pk=int(class_id), is_active=True)
        if not can_manage_diplomas(request.user, academic_class):
            return JsonResponse({"ok": False, "message": "Action non autorisee."}, status=403)
        result = prepare_diploma_awards_for_class(academic_class=academic_class, actor=request.user, publish=publish)
    except AcademicClass.DoesNotExist:
        return JsonResponse({"ok": False, "message": "Classe introuvable."}, status=404)
    return JsonResponse(
        {
            "ok": True,
            "message": f"{len(result['awards'])} diplome(s) prepare(s). {len(result['skipped'])} dossier(s) ignore(s).",
            "prepared": len(result["awards"]),
            "skipped": result["skipped"],
        }
    )


@login_required
def dg_exec_action(request):
    """Point d'entrée unique pour les actions DG réelles (nommer, diplômer, valider, arbitrer, cycle)."""
    position = get_user_position(request.user)
    if position not in {"executive_director", "deputy_executive_director"}:
        return HttpResponseForbidden("Accès réservé au Directeur Général.")
    if request.method != "POST":
        return HttpResponseBadRequest("Méthode invalide.")

    action = (request.POST.get("action") or "").strip()
    try:
        if action == "nominate_manager":
            branch_id = int(request.POST["branch_id"])
            user_id = int(request.POST["user_id"])
            result = nominate_branch_manager(actor=request.user, branch_id=branch_id, user_id=user_id)
        elif action == "deliver_diploma":
            award_id = int(request.POST["award_id"])
            result = deliver_diploma(actor=request.user, award_id=award_id)
        elif action == "validate_closure":
            closure_id = int(request.POST["closure_id"])
            result = validate_closure(actor=request.user, closure_id=closure_id)
        elif action == "arbitrate_decision":
            decision_id = int(request.POST["decision_id"])
            approve = (request.POST.get("approve") or "").strip().lower() in {"1", "true", "oui"}
            reason = (request.POST.get("reason") or "").strip()
            result = arbitrate_decision(actor=request.user, decision_id=decision_id, approve=approve, reason=reason)
        elif action == "publish_class_diplomas":
            class_id = int(request.POST["class_id"])
            result = publish_class_diplomas(actor=request.user, class_id=class_id)
        elif action == "transition_cycle":
            cycle_id = int(request.POST["cycle_id"])
            target_status = (request.POST.get("target_status") or "").strip()
            result = transition_branch_cycle(actor=request.user, cycle_id=cycle_id, target_status=target_status)
        else:
            return JsonResponse({"ok": False, "message": "Action DG inconnue."}, status=400)
    except (Branch.DoesNotExist, AcademicDiplomaAward.DoesNotExist,
            BranchMonthlyClosure.DoesNotExist, StudentYearDecision.DoesNotExist,
            KeyError, ValueError) as exc:
        return JsonResponse({"ok": False, "message": f"Erreur : {exc}"}, status=404)
    return JsonResponse(result)


@login_required
def dg_assign_manager_modal(request):
    """Popup pour choisir un utilisateur à nommer gestionnaire d'une annexe."""
    position = get_user_position(request.user)
    if position not in {"executive_director", "deputy_executive_director"}:
        return HttpResponseForbidden("Accès réservé au Directeur Général.")
    branch_id = (request.GET.get("branch_id") or "").strip()
    branch = None
    if branch_id.isdigit():
        branch = Branch.objects.filter(pk=int(branch_id), is_active=True).first()
    candidates = User.objects.filter(is_active=True).exclude(profile__position__in=["student"]).select_related("profile").order_by("last_name", "first_name")[:50]
    return render(request, "portal/dg/modals/assign_manager.html", {
        "branch": branch,
        "candidates": candidates,
    })


@login_required
def dg_closure_detail(request):
    """Drawer détaillant une clôture mensuelle."""
    position = get_user_position(request.user)
    if position not in {"executive_director", "deputy_executive_director"}:
        return HttpResponseForbidden("Accès réservé au Directeur Général.")
    closure_id = (request.GET.get("closure_id") or "").strip()
    closure = None
    if closure_id.isdigit():
        closure = BranchMonthlyClosure.objects.select_related("branch", "created_by", "validated_by").filter(pk=int(closure_id)).first()
    return render(request, "portal/dg/modals/closure_detail.html", {
        "closure": closure,
    })


@login_required
def dg_export(request):
    position = get_user_position(request.user)
    if position not in {"executive_director", "deputy_executive_director"}:
        return HttpResponseForbidden("Acces reserve au Directeur General.")
    kind = (request.GET.get("kind") or "branches").strip().lower()
    export_format = (request.GET.get("format") or "csv").strip().lower()
    context = build_dg_dashboard_context(request, _build_portal_context)
    rows = []

    class _RowWriter:
        def writerow(self, row):
            rows.append([str(value) if value is not None else "" for value in row])

    writer = _RowWriter()

    if kind == "finance":
        writer.writerow(["Annexe", "Revenus", "Depenses", "Solde", "Paiements valides", "Alertes ouvertes"])
        for item in context["branch_summaries"]:
            writer.writerow([
                item["branch"].name,
                item["revenue_total"],
                item["expense_total"],
                item["balance_total"],
                len(item["latest_payments"]),
                item["open_alert_count"],
            ])
    elif kind == "alerts":
        writer.writerow(["Gravite", "Type", "Annexe", "Description", "Responsable", "Statut", "Age"])
        for alert in context["priority_alerts"]:
            writer.writerow([
                alert.severity,
                alert.type,
                alert.branch_name,
                alert.description,
                alert.owner,
                alert.status,
                alert.age,
            ])
    elif kind == "students":
        writer.writerow(["Matricule", "Nom", "Email", "Annexe", "Formation", "Classe", "Inscription", "Solde"])
        branch_ids = [item["branch"].id for item in context["branch_summaries"]]
        students_qs = (
            Student.objects.filter(is_active=True, inscription__candidature__branch_id__in=branch_ids)
            .select_related(
                "inscription",
                "inscription__candidature",
                "inscription__candidature__branch",
                "inscription__candidature__programme",
                "current_academic_enrollment__academic_class",
            )
            .order_by("inscription__candidature__last_name", "inscription__candidature__first_name")
        )
        for student in students_qs:
            candidature = student.inscription.candidature
            writer.writerow([
                student.matricule,
                student.full_name,
                candidature.email,
                candidature.branch.name if candidature.branch else "",
                candidature.programme.title if candidature.programme else "",
                student.current_academic_enrollment.academic_class if student.current_academic_enrollment else "",
                student.inscription.reference,
                student.inscription.balance,
            ])
    elif kind == "payments":
        writer.writerow(["Date", "Annexe", "Candidat", "Reference", "Methode", "Statut", "Montant", "Agent"])
        branch_ids = [item["branch"].id for item in context["branch_summaries"]]
        payments_qs = (
            Payment.objects.filter(inscription__candidature__branch_id__in=branch_ids)
            .select_related("agent__user", "inscription__candidature", "inscription__candidature__branch")
            .order_by("-paid_at", "-id")
        )
        for payment in payments_qs:
            candidature = payment.inscription.candidature
            writer.writerow([
                payment.paid_at.strftime("%Y-%m-%d %H:%M") if payment.paid_at else "",
                candidature.branch.name if candidature.branch else "",
                str(candidature),
                payment.reference,
                payment.get_method_display(),
                payment.get_status_display(),
                payment.amount,
                payment.agent.user.get_full_name() or payment.agent.user.username if payment.agent else "",
            ])
    elif kind == "staff":
        writer.writerow(["Nom", "Email", "Poste", "Role", "Annexe", "Statut", "Salaire", "Derniere activite"])
        branch_ids = [item["branch"].id for item in context["branch_summaries"]]
        staff_qs = (
            Profile.objects.filter(
                Q(user__is_staff=True)
                | Q(position__in={
                    "teacher",
                    "finance_manager",
                    "payment_agent",
                    "secretary",
                    "admissions",
                    "director_of_studies",
                    "executive_director",
                    "deputy_executive_director",
                    "branch_manager",
                    "annex_manager",
                    "academic_supervisor",
                    "it_support",
                    "marketing_manager",
                    "super_admin",
                })
            )
            .filter(Q(branch_id__in=branch_ids) | Q(branch__isnull=True))
            .select_related("user", "branch")
            .order_by("branch__name", "position", "user__last_name")
        )
        for profile in staff_qs:
            writer.writerow([
                profile.user.get_full_name() or profile.user.username,
                profile.user.email,
                profile.get_position_display() or profile.position,
                profile.get_role_display() or profile.role,
                profile.branch.name if profile.branch else "Global",
                profile.get_employment_status_display(),
                profile.salary_base,
                profile.last_seen.strftime("%Y-%m-%d %H:%M") if profile.last_seen else "",
            ])
    elif kind == "audit":
        writer.writerow(["Date", "Action", "Acteur", "Annexe", "Cible", "Details"])
        branch_ids = [item["branch"].id for item in context["branch_summaries"]]
        audit_qs = (
            SupportAuditLog.objects.select_related("actor", "branch")
            .filter(Q(branch_id__in=branch_ids) | Q(branch__isnull=True))
            .order_by("-created_at")[:1000]
        )
        for row in audit_qs:
            writer.writerow([
                row.created_at.strftime("%Y-%m-%d %H:%M"),
                row.get_action_type_display(),
                row.actor.get_full_name() or row.actor.username if row.actor else "",
                row.branch.name if row.branch else "",
                row.target_label,
                row.details,
            ])
    else:
        writer.writerow(["Annexe", "Manager", "Etudiants", "Classes", "Inscriptions", "Candidatures", "Revenus", "Depenses", "Solde", "Performance"])
        for item in context["branch_summaries"]:
            writer.writerow([
                item["branch"].name,
                item["manager_name"],
                item["student_count"],
                item["class_count"],
                item["active_inscription_count"],
                item["candidature_count"],
                item["revenue_total"],
                item["expense_total"],
                item["balance_total"],
                item["performance_label"],
            ])
    if export_format == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = f"DG {kind}"[:31]
        for row in rows:
            sheet.append(row)
        if rows:
            header_fill = PatternFill("solid", fgColor="0F172A")
            for cell in sheet[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = header_fill
            sheet.freeze_panes = "A2"
            for column_cells in sheet.columns:
                max_length = max(len(str(cell.value or "")) for cell in column_cells)
                sheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_length + 2, 12), 42)
        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = f'attachment; filename="dg-{kind}.xlsx"'
        workbook.save(response)
        return response

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="dg-{kind}.csv"'
    csv_writer = csv.writer(response)
    for row in rows:
        csv_writer.writerow(row)
    return response


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_exam_session_action(request):
    if request.method != "POST":
        return _deny_portal_access(request)
    branch = _resolve_director_branch(request)
    if not branch:
        return HttpResponseBadRequest("Aucune annexe.")

    action = (request.POST.get("action") or "").strip()
    session_choices = (
        (AcademicCalendarEntry.EVENT_EXAM_SESSION, "Session d'examens"),
        (AcademicCalendarEntry.EVENT_RETAKE_SESSION, "Session de rattrapage"),
    )

    if action == "create":
        form = DirectorExamSessionForm(request.POST, event_type_choices=session_choices)
        if form.is_valid():
            academic_year = (
                AcademicYear.objects.filter(is_active=True).order_by("-start_date").first()
                or AcademicYear.objects.order_by("-start_date").first()
            )
            if academic_year is None:
                form.add_error(
                    None,
                    "Aucune année académique n'est configurée. Créez-la d'abord dans Calendrier.",
                )
            else:
                calendar = (
                    AcademicCalendar.objects.filter(
                        branch=branch,
                        academic_year=academic_year,
                        status=AcademicCalendar.STATUS_DRAFT,
                    )
                    .order_by("-version")
                    .first()
                )
                try:
                    if calendar is None:
                        last_version = (
                            AcademicCalendar.objects.filter(
                                branch=branch, academic_year=academic_year
                            ).aggregate(max_version=Max("version"))["max_version"]
                            or 0
                        )
                        calendar = create_calendar(
                            actor=request.user,
                            branch=branch,
                            academic_year=academic_year,
                            version=last_version + 1,
                        )

                    start_datetime = timezone.make_aware(
                        datetime.combine(form.cleaned_data["start_date"], datetime.min.time())
                    )
                    end_datetime = timezone.make_aware(
                        datetime.combine(form.cleaned_data["end_date"], datetime.max.time())
                    )
                    validate_entry_business_rules(
                        calendar=calendar,
                        event_type=form.cleaned_data["event_type"],
                        start_datetime=start_datetime,
                        end_datetime=end_datetime,
                        target_scope=AcademicCalendarEntry.SCOPE_BRANCH,
                        academic_class=None,
                        semester=None,
                    )
                    entry = create_calendar_entry(
                        actor=request.user,
                        calendar=calendar,
                        title=form.cleaned_data["title"],
                        description=form.cleaned_data["description"],
                        event_type=form.cleaned_data["event_type"],
                        start_datetime=start_datetime,
                        end_datetime=end_datetime,
                        all_day=True,
                        target_scope=AcademicCalendarEntry.SCOPE_BRANCH,
                        academic_class=None,
                        semester=None,
                        is_blocking=True,
                        status=AcademicCalendarEntry.STATUS_DRAFT,
                    )
                except ValidationError as exc:
                    form.add_error(None, " ".join(exc.messages))
                else:
                    response = _render_director_subview(
                        request,
                        section="evaluations_calendar",
                        subview="sessions",
                        template_name=_EXAM_SESSION_SUBVIEW_TEMPLATES["sessions"],
                        toast={
                            "level": "success",
                            "message": f"La session « {entry.title} » a été créée en brouillon.",
                        },
                    )
                    response["HX-Trigger"] = "directorExamSessionChanged"
                    return response

        return _render_director_subview(
            request,
            section="evaluations_calendar",
            subview="sessions",
            template_name=_EXAM_SESSION_SUBVIEW_TEMPLATES["sessions"],
            toast={"level": "error", "message": "Corrigez les champs indiqués."},
            extra={"exam_session_form": form},
        )

    if action == "cancel":
        entry_id = (request.POST.get("entry_id") or "").strip()
        reason = (request.POST.get("reason") or "").strip()
        entry = None
        if entry_id.isdigit():
            entry = AcademicCalendarEntry.objects.select_related(
                "calendar", "calendar__branch", "calendar__academic_year"
            ).filter(
                id=int(entry_id),
                calendar__branch=branch,
                event_type__in={
                    AcademicCalendarEntry.EVENT_EXAM_SESSION,
                    AcademicCalendarEntry.EVENT_RETAKE_SESSION,
                },
            ).first()
        try:
            if entry is None:
                raise ValidationError("Session introuvable ou hors annexe.")
            if not reason:
                raise ValidationError("Le motif d'annulation est obligatoire.")
            previous_status = entry.status
            update_calendar_entry(
                entry,
                actor=request.user,
                status=AcademicCalendarEntry.STATUS_CANCELLED,
            )
            log_action(
                request.user,
                "exam_session.cancelled",
                entry,
                old_values={"status": previous_status},
                new_values={"status": entry.status},
                branch=branch,
                academic_year=entry.calendar.academic_year,
                reason=reason,
                request=request,
            )
            toast = {
                "level": "success",
                "message": f"La session « {entry.title} » a été annulée.",
            }
        except ValidationError as exc:
            toast = {"level": "error", "message": " ".join(exc.messages)}
        response = _render_director_subview(
            request,
            section="evaluations_calendar",
            subview="sessions",
            template_name=_EXAM_SESSION_SUBVIEW_TEMPLATES["sessions"],
            toast=toast,
        )
        response["HX-Trigger"] = "directorExamSessionChanged"
        return response

    return _render_director_subview(
        request,
        section="evaluations_calendar",
        subview="sessions",
        template_name=_EXAM_SESSION_SUBVIEW_TEMPLATES["sessions"],
        toast={
            "level": "error",
            "message": "Cette action n'existe pas. La publication se fait depuis Calendrier.",
        },
    )


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_evaluation_action(request):
    if request.method != "POST":
        return _deny_portal_access(request)
    branch = _resolve_director_branch(request)
    if not branch:
        return HttpResponseBadRequest("Aucune annexe.")

    action = (request.POST.get("action") or "").strip()
    if action == "create":
        form = DirectorEvaluationForm(request.POST, branch=branch)
        if form.is_valid():
            academic_class = form.cleaned_data["class_id"]
            try:
                event = create_schedule_event(
                    user=request.user,
                    title=form.cleaned_data["title"],
                    description=form.cleaned_data["description"],
                    event_type=form.cleaned_data["event_type"],
                    academic_class=academic_class,
                    ec=form.cleaned_data["ec"],
                    teacher=form.cleaned_data["teacher"],
                    branch=branch,
                    academic_year=academic_class.academic_year,
                    start_datetime=form.cleaned_data["start_datetime"],
                    end_datetime=form.cleaned_data["end_datetime"],
                    status=AcademicScheduleEvent.STATUS_PLANNED,
                    location=form.cleaned_data["location"],
                    is_active=True,
                )
            except ValidationError as exc:
                form.add_error(None, " ".join(exc.messages))
            else:
                response = _render_director_subview(
                    request,
                    section="evaluations_calendar",
                    subview="scheduled",
                    template_name=_EXAM_SESSION_SUBVIEW_TEMPLATES["scheduled"],
                    toast={
                        "level": "success",
                        "message": f"L'évaluation « {event.title} » a été planifiée.",
                    },
                )
                response["HX-Trigger"] = "directorEvaluationChanged"
                return response

        return _render_director_subview(
            request,
            section="evaluations_calendar",
            subview="create",
            template_name=_EXAM_SESSION_SUBVIEW_TEMPLATES["create"],
            toast={"level": "error", "message": "Corrigez les champs indiqués."},
            extra={"evaluation_form": form},
        )

    if action == "cancel":
        event_id = (request.POST.get("event_id") or "").strip()
        reason = (request.POST.get("reason") or "").strip()
        event = None
        if event_id.isdigit():
            event = AcademicScheduleEvent.objects.filter(
                id=int(event_id),
                branch=branch,
                event_type__in=[
                    AcademicScheduleEvent.EVENT_TYPE_EXAM,
                    AcademicScheduleEvent.EVENT_TYPE_PRACTICAL,
                ],
            ).first()
        try:
            if event is None:
                raise ValidationError("Évaluation introuvable ou hors annexe.")
            cancel_schedule_event(event, reason, request.user)
            toast = {
                "level": "success",
                "message": f"L'évaluation « {event.title} » a été annulée.",
            }
        except ValidationError as exc:
            toast = {"level": "error", "message": " ".join(exc.messages)}
        response = _render_director_subview(
            request,
            section="evaluations_calendar",
            subview="scheduled",
            template_name=_EXAM_SESSION_SUBVIEW_TEMPLATES["scheduled"],
            toast=toast,
        )
        response["HX-Trigger"] = "directorEvaluationChanged"
        return response

    return _render_director_subview(
        request,
        section="evaluations_calendar",
        subview="overview",
        template_name=_EXAM_SESSION_SUBVIEW_TEMPLATES["overview"],
        toast={"level": "error", "message": "Action d'évaluation inconnue."},
    )


@_position_required(DIRECTOR_DASHBOARD_POSITIONS)
def director_calendar_action(request):
    """
    Point d'entree unique pour toutes les actions de gestion du calendrier academique.
    Actions supportees :
      create_calendar, validate_calendar, publish_calendar, archive_calendar
      add_entry, edit_entry, delete_entry
    Retourne toujours workspace.html section=calendrier (HTMX swap).
    """
    if request.method != "POST":
        return _deny_portal_access(request)
    branch = _resolve_director_branch(request)
    if not branch:
        return HttpResponseBadRequest("Aucune annexe.")

    from datetime import datetime as _dt
    from academics.models import (
        AcademicCalendar as _Cal,
        AcademicCalendarEntry as _Entry,
        AcademicYear as _Year,
        AcademicClass as _Class,
    )
    from academics.services.calendar_service import (
        create_calendar,
        delete_calendar,
        validate_calendar,
        publish_calendar,
        archive_calendar,
        create_calendar_entry,
        update_calendar_entry,
        delete_calendar_entry,
    )
    from portal.services.director.calendar_mgt_service import (
        validate_entry_business_rules,
        _next_version_for,
    )

    action = (request.POST.get("action") or "").strip()
    cal_id_raw = (request.POST.get("calendar_id") or "").strip()
    toast = None
    redirect_cal_id = cal_id_raw if cal_id_raw.isdigit() else None

    def _require_calendar(cid):
        if not cid.isdigit():
            raise ValidationError("Identifiant de calendrier invalide.")
        cal = _Cal.objects.filter(id=int(cid), branch=branch).select_related(
            "academic_year", "branch"
        ).first()
        if not cal:
            raise ValidationError(
                "Calendrier introuvable ou vous n'avez pas acc\u00e8s \u00e0 ce calendrier."
            )
        return cal

    def _parse_date(raw, hour=0, minute=0):
        """Parse une date YYYY-MM-DD en datetime aware."""
        try:
            naive = _dt.strptime(raw.strip(), "%Y-%m-%d").replace(hour=hour, minute=minute)
            return timezone.make_aware(naive)
        except ValueError:
            raise ValidationError(
                f"Format de date invalide : {raw!r}. Format attendu : AAAA-MM-JJ."
            )

    def _extract_entry_fields():
        """Extrait et valide les champs communs des formulaires add/edit entry."""
        title = (request.POST.get("title") or "").strip()
        event_type = (request.POST.get("event_type") or "").strip()
        start_raw = (request.POST.get("start_date") or "").strip()
        end_raw = (request.POST.get("end_date") or "").strip()
        scope = (request.POST.get("target_scope") or "branch").strip()
        class_id = (request.POST.get("class_id") or "").strip()
        semester_id = (request.POST.get("semester_id") or "").strip()
        is_blocking = request.POST.get("is_blocking") == "1"
        description = (request.POST.get("description") or "").strip()

        if not title:
            raise ValidationError("L'intitul\u00e9 de l'entr\u00e9e est obligatoire.")
        if not event_type:
            raise ValidationError("Le type d'\u00e9v\u00e9nement est obligatoire.")
        if not start_raw:
            raise ValidationError("La date de d\u00e9but est obligatoire.")
        if not end_raw:
            raise ValidationError("La date de fin est obligatoire.")

        start_dt = _parse_date(start_raw, hour=0, minute=0)
        end_dt = _parse_date(end_raw, hour=23, minute=59)

        if end_dt <= start_dt:
            raise ValidationError(
                "La date de fin doit \u00eatre post\u00e9rieure \u00e0 la date de d\u00e9but."
            )

        academic_class = None
        if class_id.isdigit():
            academic_class = _Class.objects.filter(
                id=int(class_id), branch=branch
            ).first()
            if not academic_class:
                raise ValidationError("Classe introuvable ou hors p\u00e9rim\u00e8tre.")

        semester = None
        if semester_id.isdigit():
            semester = Semester.objects.filter(
                id=int(semester_id),
                academic_class__branch=branch,
            ).select_related("academic_class").first()
            if not semester:
                raise ValidationError("Semestre introuvable ou hors p\u00e9rim\u00e8tre.")

        return dict(
            title=title, event_type=event_type,
            start_dt=start_dt, end_dt=end_dt,
            scope=scope, academic_class=academic_class,
            semester=semester, is_blocking=is_blocking,
            description=description,
        )

    try:
        # ------------------------------------------------------------------
        # Gestion du calendrier
        # ------------------------------------------------------------------
        if action == "create_academic_year":
            from datetime import date as _date
            year_name = (request.POST.get("year_name") or "").strip()
            year_start_raw = (request.POST.get("year_start") or "").strip()
            year_end_raw = (request.POST.get("year_end") or "").strip()
            import re
            if not re.fullmatch(r"\d{4}-\d{4}", year_name):
                raise ValidationError(
                    "Le nom doit respecter le format AAAA-AAAA (ex\u00e9mple\u00a0: 2027-2028)."
                )
            if not year_start_raw or not year_end_raw:
                raise ValidationError("Les dates de d\u00e9but et de fin sont obligatoires.")
            try:
                year_start = _date.fromisoformat(year_start_raw)
                year_end = _date.fromisoformat(year_end_raw)
            except ValueError:
                raise ValidationError("Format de date invalide. Utilisez AAAA-MM-JJ.")
            if year_start >= year_end:
                raise ValidationError(
                    "La date de fin doit \u00eatre post\u00e9rieure \u00e0 la date de d\u00e9but."
                )
            if _Year.objects.filter(name=year_name).exists():
                raise ValidationError(
                    f"L'ann\u00e9e acad\u00e9mique \u00ab\u00a0{year_name}\u00a0\u00bb existe d\u00e9j\u00e0."
                )
            year = _Year(
                name=year_name,
                start_date=year_start,
                end_date=year_end,
                is_active=False,
            )
            year.full_clean()
            year.save()
            toast = {
                "level": "success",
                "message": (
                    f"Ann\u00e9e acad\u00e9mique \u00ab\u00a0{year_name}\u00a0\u00bb cr\u00e9\u00e9e. "
                    f"Vous pouvez maintenant cr\u00e9er un calendrier pour cette ann\u00e9e."
                ),
            }

        elif action == "create_calendar":
            year_id_raw = (request.POST.get("academic_year_id") or "").strip()
            if not year_id_raw.isdigit():
                raise ValidationError("Ann\u00e9e acad\u00e9mique invalide.")
            year = _Year.objects.filter(id=int(year_id_raw)).first()
            if not year:
                raise ValidationError("Ann\u00e9e acad\u00e9mique introuvable.")
            # Version auto-incrementee
            version = _next_version_for(branch, year)
            cal = create_calendar(
                actor=request.user, branch=branch,
                academic_year=year, version=version,
            )
            redirect_cal_id = str(cal.id)
            toast = {
                "level": "success",
                "message": (
                    f"Calendrier {year.name} \u2014 Version {cal.version} "
                    f"cr\u00e9\u00e9 en brouillon."
                ),
            }

        elif action == "validate_calendar":
            cal = _require_calendar(cal_id_raw)
            validate_calendar(cal, actor=request.user)
            toast = {
                "level": "success",
                "message": (
                    f"Calendrier {cal.academic_year.name} valid\u00e9. "
                    f"V\u00e9rifiez les entr\u00e9es puis publiez-le."
                ),
            }

        elif action == "publish_calendar":
            cal = _require_calendar(cal_id_raw)
            publish_calendar(cal, actor=request.user)
            toast = {
                "level": "success",
                "message": (
                    f"Calendrier {cal.academic_year.name} publi\u00e9. "
                    f"Il est maintenant visible par tous les utilisateurs de l'annexe."
                ),
            }

        elif action == "delete_calendar":
            cal = _require_calendar(cal_id_raw)
            cal_name = str(cal.academic_year.name)
            delete_calendar(cal, actor=request.user)
            toast = {
                "level": "success",
                "message": f"Calendrier {cal_name} supprim\u00e9.",
            }
            redirect_cal_id = None

        elif action == "archive_calendar":
            cal = _require_calendar(cal_id_raw)
            archive_calendar(cal, actor=request.user)
            toast = {
                "level": "success",
                "message": f"Calendrier {cal.academic_year.name} archiv\u00e9.",
            }
            redirect_cal_id = None

        # ------------------------------------------------------------------
        # Gestion des entrees
        # ------------------------------------------------------------------
        elif action == "add_entry":
            cal = _require_calendar(cal_id_raw)
            if cal.status != _Cal.STATUS_DRAFT:
                raise ValidationError(
                    "Seul un calendrier en brouillon peut recevoir de nouvelles entr\u00e9es."
                )
            f = _extract_entry_fields()
            validate_entry_business_rules(
                calendar=cal,
                event_type=f["event_type"],
                start_datetime=f["start_dt"],
                end_datetime=f["end_dt"],
                target_scope=f["scope"],
                academic_class=f["academic_class"],
                semester=f["semester"],
            )
            create_calendar_entry(
                actor=request.user,
                calendar=cal,
                title=f["title"],
                event_type=f["event_type"],
                start_datetime=f["start_dt"],
                end_datetime=f["end_dt"],
                target_scope=f["scope"],
                academic_class=f["academic_class"],
                semester=f["semester"],
                is_blocking=f["is_blocking"],
                description=f["description"],
                status=_Entry.STATUS_DRAFT,
            )
            toast = {
                "level": "success",
                "message": f"Entr\u00e9e \u00ab {f['title']} \u00bb ajout\u00e9e.",
            }

        elif action == "edit_entry":
            cal = _require_calendar(cal_id_raw)
            if cal.status != _Cal.STATUS_DRAFT:
                raise ValidationError(
                    "Ce calendrier n'est plus en brouillon et ne peut pas \u00eatre modifi\u00e9."
                )
            entry_id_raw = (request.POST.get("entry_id") or "").strip()
            if not entry_id_raw.isdigit():
                raise ValidationError("Identifiant d'entr\u00e9e invalide.")
            entry = _Entry.objects.filter(
                id=int(entry_id_raw), calendar=cal
            ).first()
            if not entry:
                raise ValidationError("Entr\u00e9e introuvable ou hors p\u00e9rim\u00e8tre.")
            f = _extract_entry_fields()
            validate_entry_business_rules(
                calendar=cal,
                event_type=f["event_type"],
                start_datetime=f["start_dt"],
                end_datetime=f["end_dt"],
                target_scope=f["scope"],
                academic_class=f["academic_class"],
                semester=f["semester"],
                exclude_entry_id=entry.id,
            )
            update_calendar_entry(
                entry,
                actor=request.user,
                title=f["title"],
                event_type=f["event_type"],
                start_datetime=f["start_dt"],
                end_datetime=f["end_dt"],
                target_scope=f["scope"],
                academic_class=f["academic_class"],
                semester=f["semester"],
                is_blocking=f["is_blocking"],
                description=f["description"],
            )
            toast = {
                "level": "success",
                "message": f"Entr\u00e9e \u00ab {f['title']} \u00bb mise \u00e0 jour.",
            }

        elif action == "delete_entry":
            entry_id_raw = (request.POST.get("entry_id") or "").strip()
            if not entry_id_raw.isdigit():
                raise ValidationError("Identifiant d'entr\u00e9e invalide.")
            entry = _Entry.objects.filter(
                id=int(entry_id_raw), calendar__branch=branch
            ).select_related("calendar").first()
            if not entry:
                raise ValidationError("Entr\u00e9e introuvable ou hors p\u00e9rim\u00e8tre.")
            redirect_cal_id = str(entry.calendar_id)
            entry_title = entry.title
            delete_calendar_entry(entry, actor=request.user)
            toast = {
                "level": "success",
                "message": f"Entr\u00e9e \u00ab {entry_title} \u00bb supprim\u00e9e.",
            }

        else:
            raise ValidationError(f"Action non reconnue : {action!r}")

    except ValidationError as exc:
        # Extraire le message lisible, qu'il vienne d'un dict ou d'une liste
        msgs = getattr(exc, "message_dict", None)
        if msgs:
            msg = " | ".join(
                f"{v[0]}" if isinstance(v, list) else str(v)
                for v in msgs.values()
            )
        elif hasattr(exc, "messages") and isinstance(exc.messages, list):
            msg = " | ".join(str(m) for m in exc.messages)
        else:
            msg = getattr(exc, "message", str(exc))
        toast = {"level": "error", "message": msg}
    except PermissionDenied as exc:
        toast = {"level": "error", "message": str(exc) or "Acc\u00e8s refus\u00e9."}
    except Exception as exc:
        import logging
        logging.getLogger(__name__).exception("director_calendar_action inattendue")
        toast = {
            "level": "error",
            "message": f"Erreur inattendue : {exc}",
        }

    # Rendre le workspace section=calendrier avec le contexte mis a jour
    original_get = request.GET
    params = request.GET.copy()
    params["section"] = "calendrier"
    if redirect_cal_id:
        params["calendar_id"] = redirect_cal_id
    request.GET = params
    try:
        context = _build_director_workspace_context(request, toast=toast)
    finally:
        request.GET = original_get
    return render(request, "portal/staff/director/partials/workspace.html", context)
    return render(request, "portal/staff/director/partials/workspace.html", context)
