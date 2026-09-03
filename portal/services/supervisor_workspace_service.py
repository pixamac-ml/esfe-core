"""Branch-scoped workspace contracts for the operational supervisor dashboard."""

from datetime import datetime, timedelta
from urllib.parse import urlencode

from django.db.models import Count, Q
from django.core.paginator import Paginator
from django.utils import timezone

from academics.models import AcademicClass, AcademicScheduleEvent
from portal.services.supervisor_dashboard_service import get_supervisor_class_picker_bundle
from portal.services.director.timetable_service import build_weekly_timetable_grid
from portal.services.supervisor_service import (
    build_attendance_monthly_report_context,
    build_attendance_section_context,
    build_home_section_context,
    build_schedule_section_context,
    build_students_section_context,
    build_teachers_section_context,
    build_teachers_weekly_report_context,
)
from students.models import (
    AttendanceAlert,
    Student,
    StudentAttendance,
    StudentCase,
    TeacherAttendance,
    TeacherCase,
)
from portal.services.supervisor_service import SUPERVISOR_LIST_PAGE_SIZE


SECTION_META = {
    "home": (
        "Supervision opérationnelle",
        "Accueil",
        "Suivez les séances, les présences et les anomalies de votre annexe.",
    ),
    "classes": (
        "Périmètre de l'annexe",
        "Classes",
        "Consultez les classes et leurs effectifs sans modifier l'organisation académique.",
    ),
    "attendance": (
        "Assiduité",
        "Présence des étudiants",
        "Renseignez les présences uniquement pour les séances réellement programmées.",
    ),
    "teachers": (
        "Supervision des cours",
        "Séances à superviser",
        "Rapprochez le planning officiel, la déclaration de l’enseignant et le constat terrain avant toute validation.",
    ),
    "schedule": (
        "Organisation publiée",
        "Emploi du temps",
        "Consultez le planning publié par le Directeur des études en lecture seule.",
    ),
    "signals": (
        "Transmission au DE",
        "Signalements",
        "Décrivez les faits puis transmettez-les automatiquement au Directeur des études.",
    ),
    "reports": (
        "Suivi et historique",
        "Rapports",
        "Consultez les synthèses d'assiduité et les signalements déjà transmis.",
    ),
}

SECTION_VIEWS = {
    "home": {"overview"},
    "classes": {"overview", "students"},
    "attendance": {"overview", "call", "history", "alerts"},
    "teachers": {"overview", "today", "history"},
    "schedule": {"today", "week"},
    "signals": {"overview", "new", "transmitted"},
    "reports": {"overview", "students", "teachers", "transmitted"},
}

DEFAULT_VIEWS = {
    "home": "overview",
    "classes": "overview",
    "attendance": "call",
    "teachers": "today",
    # The schedule section is class-centred: open directly on the published
    # weekly grid, not on a branch-wide summary of today's sessions.
    "schedule": "week",
    "signals": "overview",
    "reports": "overview",
}

# The active class is a working context, not a one-shot display filter.  The
# URL remains the shareable source when present; the session keeps that context
# while the supervisor moves through independent dashboard sections.
ACTIVE_CLASS_SESSION_KEY = "supervisor_active_class_id"

LEGACY_SECTIONS = {
    "attendance_report": ("attendance", "history"),
    "students": ("classes", "students"),
    "teachers_report": ("teachers", "history"),
    "cases": ("signals", "transmitted"),
    "courses": ("schedule", "week"),
}

SUBCONTENT_TEMPLATES = {
    ("home", "overview"): "portal/staff/supervisor/partials/panel_home.html",
    ("classes", "overview"): "portal/staff/supervisor/partials/panel_classes.html",
    ("classes", "students"): "portal/staff/supervisor/partials/panel_students.html",
    ("attendance", "overview"): "portal/staff/supervisor/partials/panel_attendance_overview.html",
    ("attendance", "call"): "portal/staff/supervisor/partials/panel_attendance.html",
    ("attendance", "history"): "portal/staff/supervisor/partials/panel_attendance_report.html",
    ("attendance", "alerts"): "portal/staff/supervisor/partials/panel_attendance_alerts.html",
    ("teachers", "overview"): "portal/staff/supervisor/partials/panel_teachers_overview.html",
    ("teachers", "today"): "portal/staff/supervisor/partials/panel_teachers.html",
    ("teachers", "history"): "portal/staff/supervisor/partials/panel_teachers_report.html",
    ("schedule", "today"): "portal/staff/supervisor/partials/panel_schedule_today.html",
    ("schedule", "week"): "portal/staff/supervisor/partials/panel_schedule.html",
    ("signals", "overview"): "portal/staff/supervisor/partials/panel_signals_overview.html",
    ("signals", "new"): "portal/staff/supervisor/partials/panel_signal_form.html",
    ("signals", "transmitted"): "portal/staff/supervisor/partials/panel_signals_list.html",
    ("reports", "overview"): "portal/staff/supervisor/partials/panel_reports_overview.html",
    ("reports", "students"): "portal/staff/supervisor/partials/panel_attendance_report.html",
    ("reports", "teachers"): "portal/staff/supervisor/partials/panel_teachers_report.html",
    ("reports", "transmitted"): "portal/staff/supervisor/partials/panel_signals_list.html",
}

STUDENT_SIGNAL_TYPES = (
    (StudentCase.TYPE_ABSENCE_REPETEE, "Absences répétées"),
    (StudentCase.TYPE_RETARD_FREQUENT, "Retards fréquents"),
    (StudentCase.TYPE_ABSENCE_LONGUE, "Absence longue"),
    (StudentCase.TYPE_SIGNALEMENT_COMPORTEMENTAL, "Incident disciplinaire"),
)

TEACHER_SIGNAL_TYPES = (
    (TeacherCase.TYPE_RETARD_REPETE, "Retard important ou répété"),
    (TeacherCase.TYPE_ABSENCE_NON_JUSTIFIEE, "Enseignant absent"),
    (TeacherCase.TYPE_APPEL_NON_FAIT, "Cours ou appel non assuré"),
    (TeacherCase.TYPE_INCIDENT, "Incident constaté"),
    (TeacherCase.TYPE_AUTRE, "Autre fait opérationnel"),
)


def resolve_section_view(request, *, section=None):
    raw_section = (
        section
        or request.GET.get("section")
        or request.POST.get("section")
        or "home"
    ).strip().lower()
    legacy = LEGACY_SECTIONS.get(raw_section)
    if legacy:
        resolved_section, legacy_view = legacy
    else:
        resolved_section = raw_section if raw_section in SECTION_VIEWS else "home"
        legacy_view = None
    raw_view = (request.GET.get("view") or request.POST.get("view") or legacy_view or "").strip().lower()
    active_view = raw_view if raw_view in SECTION_VIEWS[resolved_section] else DEFAULT_VIEWS[resolved_section]
    return resolved_section, active_view


def _parse_date(value, fallback):
    try:
        return datetime.strptime((value or "").strip(), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return fallback


def _selected_class(branch, raw_id):
    if not str(raw_id or "").isdigit():
        return None
    return (
        AcademicClass.objects.select_related("programme", "academic_year", "branch")
        .annotate(student_count=Count("enrollments", filter=Q(enrollments__is_active=True)))
        .filter(branch=branch, is_active=True, pk=int(raw_id))
        .first()
    )


def _resolve_active_class(request, branch):
    """Resolve and persist a branch-scoped class context for the workspace."""
    session = getattr(request, "session", None)
    has_explicit_value = "class_id" in request.GET or "class_id" in request.POST
    raw_id = request.GET.get("class_id") or request.POST.get("class_id")
    if not has_explicit_value:
        raw_id = session.get(ACTIVE_CLASS_SESSION_KEY) if session is not None else None

    selected_class = _selected_class(branch, raw_id)
    if has_explicit_value and session is not None:
        if selected_class is not None:
            request.session[ACTIVE_CLASS_SESSION_KEY] = str(selected_class.id)
        else:
            request.session.pop(ACTIVE_CLASS_SESSION_KEY, None)
    elif raw_id and selected_class is None and session is not None:
        # A class archived or moved out of the branch must not survive as a
        # stale context in the session.
        request.session.pop(ACTIVE_CLASS_SESSION_KEY, None)
    return selected_class


def _signalment_rows(branch, *, transmitted_only=False):
    student_cases = list(
        StudentCase.objects.select_related(
            "student__inscription__candidature",
            "opened_by",
            "academic_class",
            "schedule_event__ec",
        )
        .prefetch_related("notes")
        .filter(branch=branch)
        .order_by("-created_at")
    )
    teacher_cases = list(
        TeacherCase.objects.select_related(
            "teacher",
            "opened_by",
            "academic_class",
            "schedule_event__ec",
        )
        .prefetch_related("notes")
        .filter(branch=branch)
        .order_by("-created_at")
    )
    rows = []
    for kind, case in [
        *(("student", case) for case in student_cases),
        *(("teacher", case) for case in teacher_cases),
    ]:
        transmitted = (
            case.status == StudentCase.STATUS_ESCALADE
            if kind == "student"
            else any(
                note.content == "Cas transmis à la Direction des études."
                for note in case.notes.all()
            )
        )
        if transmitted_only and not transmitted:
            continue
        person = (
            case.student.full_name
            if kind == "student"
            else (case.teacher.get_full_name() or case.teacher.username)
        )
        rows.append(
            {
                "kind": kind,
                "case": case,
                "person": person,
                "class_name": getattr(case.academic_class, "display_name", "") or "—",
                "session_label": (
                    f"{case.schedule_event.ec.title} · "
                    f"{timezone.localtime(case.schedule_event.start_datetime):%d/%m/%Y %H:%M}"
                    if case.schedule_event_id
                    else "Séance historique non renseignée"
                ),
                "transmitted": transmitted,
            }
        )
    rows.sort(key=lambda row: row["case"].created_at, reverse=True)
    return rows


def _signal_form_context(branch):
    today = timezone.localdate()
    sessions = list(
        AcademicScheduleEvent.objects.select_related(
            "academic_class",
            "teacher",
            "ec",
        )
        .filter(
            branch=branch,
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            is_active=True,
            start_datetime__date__gte=today - timedelta(days=30),
            start_datetime__date__lte=today,
        )
        .exclude(
            status__in={
                AcademicScheduleEvent.STATUS_DRAFT,
                AcademicScheduleEvent.STATUS_CANCELLED,
            }
        )
        .order_by("-start_datetime")[:200]
    )
    students = list(
        Student.objects.select_related("inscription__candidature")
        .filter(inscription__candidature__branch=branch, is_active=True)
        .order_by(
            "inscription__candidature__last_name",
            "inscription__candidature__first_name",
        )[:250]
    )
    teacher_ids = {event.teacher_id for event in sessions}
    teachers = sorted(
        {event.teacher for event in sessions if event.teacher_id},
        key=lambda user: (user.get_full_name() or user.username).lower(),
    )
    return {
        "signal_sessions": sessions,
        "signal_students": students,
        "signal_teachers": teachers,
        "signal_teacher_ids": teacher_ids,
        "student_signal_types": STUDENT_SIGNAL_TYPES,
        "teacher_signal_types": TEACHER_SIGNAL_TYPES,
        "signal_priorities": StudentCase.PRIORITY_CHOICES,
    }


def build_supervisor_workspace_context(request, *, branch, section=None, toast=None):
    resolved_section, active_view = resolve_section_view(request, section=section)
    _, class_picker_items, classes_qs = get_supervisor_class_picker_bundle(branch=branch)
    selected_class = _resolve_active_class(request, branch)
    crumb, panel_title, panel_lede = SECTION_META[resolved_section]
    today = timezone.localdate()
    week_start = _parse_date(
        request.GET.get("week_start") or request.POST.get("week_start"),
        today - timedelta(days=today.weekday()),
    )
    month_raw = (request.GET.get("month") or request.POST.get("month") or "").strip()
    try:
        report_month = datetime.strptime(month_raw, "%Y-%m").date().replace(day=1)
    except ValueError:
        report_month = today.replace(day=1)

    context = {
        "branch": branch,
        "section": resolved_section,
        "active_view": active_view,
        "crumb": crumb,
        "panel_title": panel_title,
        "panel_lede": panel_lede,
        "today": today,
        "class_picker_items": class_picker_items,
        "total_classes": classes_qs.count(),
        "selected_class": selected_class,
        "selected_class_id": selected_class.id if selected_class else None,
        "selected_class_label": selected_class.display_name if selected_class else "",
        "supervisor_subcontent_template": SUBCONTENT_TEMPLATES[(resolved_section, active_view)],
        "supervisor_dashboard_base_url": "/portal/dashboard/",
    }
    pagination_params = request.GET.copy() if request.GET else request.POST.copy()
    pagination_params["section"] = resolved_section
    pagination_params["view"] = active_view
    pagination_params["fragment"] = "subcontent"
    canonical_params = pagination_params.copy()
    canonical_params.pop("fragment", None)
    context["supervisor_pagination_query"] = urlencode(list(pagination_params.lists()), doseq=True)
    context["supervisor_canonical_query"] = urlencode(list(canonical_params.lists()), doseq=True)
    if toast:
        context["toast"] = toast

    if branch is None:
        return context

    if resolved_section == "home":
        context.update(build_home_section_context(branch=branch, selected_class=selected_class))

    elif resolved_section == "classes":
        class_page = Paginator(class_picker_items, SUPERVISOR_LIST_PAGE_SIZE).get_page(
            request.GET.get("classes_page") or request.POST.get("classes_page") or 1
        )
        context.update(
            {
                "class_picker_page": class_page,
                "classes_query_suffix": "section=classes&view=overview",
            }
        )
        if active_view == "students" and selected_class:
            context.update(
                build_students_section_context(
                    request=request,
                    branch=branch,
                    academic_class=selected_class,
                )
            )

    elif resolved_section == "attendance":
        attendance_today = StudentAttendance.objects.filter(branch=branch, date=today)
        context.update(
            {
                "attendance_today_total": attendance_today.count(),
                "attendance_today_present": attendance_today.filter(status=StudentAttendance.STATUS_PRESENT).count(),
                "attendance_today_absent": attendance_today.filter(status=StudentAttendance.STATUS_ABSENT).count(),
                "attendance_today_late": attendance_today.filter(status=StudentAttendance.STATUS_LATE).count(),
            }
        )
        if active_view == "call" and selected_class:
            context.update(
                build_attendance_section_context(
                    request=request,
                    branch=branch,
                    academic_class=selected_class,
                    roll_date=_parse_date(
                        request.GET.get("roll_date") or request.POST.get("roll_date"),
                        today,
                    ),
                )
            )
        elif active_view == "history" and selected_class:
            context.update(
                build_attendance_monthly_report_context(
                    branch=branch,
                    academic_class=selected_class,
                    month=report_month,
                    page_number=request.GET.get("students_report_page") or request.POST.get("students_report_page") or 1,
                )
            )
        elif active_view == "alerts":
            context["attendance_alerts"] = list(
                AttendanceAlert.objects.select_related(
                    "student__inscription__candidature"
                )
                .filter(branch=branch, is_resolved=False)
                .order_by("-triggered_at")
            )
            alerts_page = Paginator(context["attendance_alerts"], SUPERVISOR_LIST_PAGE_SIZE).get_page(
                request.GET.get("alerts_page") or request.POST.get("alerts_page") or 1
            )
            context["attendance_alerts"] = alerts_page.object_list
            context["attendance_alerts_page"] = alerts_page

    elif resolved_section == "teachers":
        teacher_session_date = _parse_date(
            request.GET.get("session_date") or request.POST.get("session_date"),
            today,
        )
        context["teacher_session_date"] = teacher_session_date
        context["teacher_session_date_iso"] = teacher_session_date.isoformat()
        context.update(
            build_teachers_section_context(
                branch=branch,
                academic_class=selected_class,
                session_date=teacher_session_date,
                page_number=request.GET.get("teachers_page") or request.POST.get("teachers_page") or 1,
            )
        )
        if active_view == "history":
            context.update(
                build_teachers_weekly_report_context(
                    branch=branch,
                    week_start=week_start,
                    page_number=request.GET.get("teachers_report_page") or request.POST.get("teachers_report_page") or 1,
                )
            )

    elif resolved_section == "schedule":
        home = build_home_section_context(branch=branch, selected_class=selected_class)
        context["home_today_sessions"] = home["home_today_sessions"]
        if active_view == "week" and selected_class:
            # Same official weekly-grid contract as the DE, read-only here.
            context["supervisor_timetable_grid"] = build_weekly_timetable_grid(
                selected_class,
                week_start=week_start,
            )
            context.update(
                build_schedule_section_context(
                branch=branch,
                academic_class=selected_class,
                week_start=week_start,
                page_number=request.GET.get("schedule_page") or request.POST.get("schedule_page") or 1,
                )
            )

    elif resolved_section == "signals":
        rows = _signalment_rows(branch, transmitted_only=active_view == "transmitted")
        rows_page = Paginator(rows, SUPERVISOR_LIST_PAGE_SIZE).get_page(
            request.GET.get("signals_page") or request.POST.get("signals_page") or 1
        )
        context.update(
            {
                "signalment_rows": rows_page.object_list,
                "signalment_rows_page": rows_page,
                "signalment_total": len(rows),
                "signalment_transmitted": sum(1 for row in rows if row["transmitted"]),
            }
        )
        if active_view == "new":
            context.update(_signal_form_context(branch))

    elif resolved_section == "reports":
        transmitted_rows = _signalment_rows(branch, transmitted_only=True)
        transmitted_page = Paginator(transmitted_rows, SUPERVISOR_LIST_PAGE_SIZE).get_page(
            request.GET.get("signals_page") or request.POST.get("signals_page") or 1
        )
        context.update(
            {
                "report_student_records": StudentAttendance.objects.filter(branch=branch).count(),
                "report_teacher_records": TeacherAttendance.objects.filter(branch=branch).count(),
                "signalment_rows": transmitted_page.object_list,
                "signalment_rows_page": transmitted_page,
                "report_transmitted_count": len(transmitted_rows),
            }
        )
        if active_view == "students" and selected_class:
            context.update(
                build_attendance_monthly_report_context(
                    branch=branch,
                    academic_class=selected_class,
                    month=report_month,
                    page_number=request.GET.get("students_report_page") or request.POST.get("students_report_page") or 1,
                )
            )
        elif active_view == "teachers":
            context.update(
                build_teachers_weekly_report_context(
                    branch=branch,
                    week_start=week_start,
                    page_number=request.GET.get("teachers_report_page") or request.POST.get("teachers_report_page") or 1,
                )
            )

    return context
