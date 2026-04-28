from datetime import timedelta

from django.db.models import Count
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.dashboards.helpers import get_user_branch
from accounts.access import can_access, get_user_position, get_user_scope
from portal.permissions import get_post_login_portal_url, get_user_role as get_portal_user_role
from secretary.permissions import is_secretary
from branches.models import Branch
from academics.models import AcademicClass, AcademicEnrollment, AcademicScheduleEvent
from academics.services.schedule_service import get_director_schedule_overview


def _build_portal_context(request, *, page_title, module_cards):
    scope = get_user_scope(request.user)
    user_display_name = request.user.get_full_name() or request.user.username

    return {
        "page_title": page_title,
        "user_display_name": user_display_name,
        "detected_role": scope.get("role") or "public",
        "scope": scope,
        "module_cards": module_cards,
        "secretary_available": is_secretary(request.user),
        "secretary_url": reverse("secretary:secretary_dashboard"),
        "welcome_message": f"Bienvenue {user_display_name}, vous etes connecte en tant que {scope.get('role') or 'public'}",
    }


def _resolve_academic_branch(request):
    branch = get_user_branch(request.user)
    if branch:
        return branch
    return (
        Branch.objects
        .annotate(schedule_count=Count("schedule_events"))
        .order_by("-schedule_count", "name")
        .first()
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


def _deny_portal_access(request):
    return HttpResponseForbidden("Acces portail refuse.")


def _position_required(expected_positions):
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            position = get_user_position(request.user)
            if position not in expected_positions:
                return _deny_portal_access(request)
            return view_func(request, *args, **kwargs)
        return login_required(wrapper)
    return decorator


@login_required
def portal_home(request):
    return redirect(get_post_login_portal_url(request.user))


@login_required
def portal_dashboard(request):
    return redirect(get_post_login_portal_url(request.user))


@login_required
def student_portal(request):
    if not can_access(request.user, "view_portal", "student"):
        return _deny_portal_access(request)
    return redirect("portal_student:dashboard")


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


@login_required
def teacher_portal(request):
    if not can_access(request.user, "view_portal", "teacher"):
        return _deny_portal_access(request)

    context = _build_portal_context(
        request,
        page_title="Portail enseignant",
        module_cards=[
            "Cours",
            "Evaluations",
            "Documents",
            "Classes",
        ],
    )
    return render(request, "portal/teacher.html", context)


@_position_required({"finance_manager", "payment_agent"})
def finance_portal(request):
    return redirect("accounts:finance_dashboard")


@_position_required({"secretary"})
def secretary_portal(request):
    return redirect("secretary:secretary_dashboard")


@_position_required({"admissions"})
def admissions_portal(request):
    return redirect("accounts:admissions_dashboard")


@_position_required({"director_of_studies", "executive_director", "super_admin"})
def director_portal(request):
    context = _build_academic_dashboard_context(
        request,
        page_title="Dashboard Direction des Etudes",
        page_kicker="Direction des etudes",
        sidebar_links=[
            {"label": "Vue generale", "href": "#overview"},
            {"label": "Programmation", "href": "#programming"},
            {"label": "Classes", "href": "#classes"},
            {"label": "Alertes", "href": "#alerts"},
        ],
        highlight=[
            "Qualite academique",
            "Pilotage des classes",
            "Suivi des enseignants",
            "Alertes et planification",
        ],
    )
    return render(request, "portal/staff/director_dashboard.html", context)


@_position_required({"academic_supervisor"})
def supervisor_portal(request):
    context = _build_academic_dashboard_context(
        request,
        page_title="Dashboard Surveillant General",
        page_kicker="Surveillance generale",
        sidebar_links=[
            {"label": "Vue generale", "href": "#overview"},
            {"label": "Emploi du temps", "href": "#timetable"},
            {"label": "Classes", "href": "#classes"},
            {"label": "Alertes", "href": "#alerts"},
        ],
        highlight=[
            "Presence et discipline",
            "Controle des classes",
            "Suivi des mouvements",
            "Alertes de surveillance",
        ],
    )
    return render(request, "portal/staff/supervisor_dashboard.html", context)


@_position_required({"it_support"})
def it_portal(request):
    branch = _resolve_academic_branch(request)
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=7)
    overview = get_director_schedule_overview(branch, week_start) if branch else {"stats": {}, "quality": {"score": 0, "warnings": []}, "alerts": [], "timetable": []}

    total_users = request.user.__class__.objects.count()
    total_active_staff = request.user.__class__.objects.filter(is_active=True, profile__user_type="staff").count()
    total_students = request.user.__class__.objects.filter(profile__role="student").count()
    recent_events = list(
        AcademicScheduleEvent.objects.select_related("branch", "academic_class", "teacher")
        .filter(start_datetime__date__gte=week_start, start_datetime__date__lt=week_end)
        .order_by("-updated_at", "-created_at")[:8]
    )

    context = {
        **_build_portal_context(
            request,
            page_title="Dashboard Informaticien",
            module_cards=[
                "Support utilisateurs",
                "Acces et comptes",
                "Sante du portail",
                "Maintenance academique",
            ],
        ),
        "dashboard_kind": "Support technique",
        "branch": branch,
        "week_start": week_start,
        "week_end": week_end,
        "total_users": total_users,
        "total_active_staff": total_active_staff,
        "total_students": total_students,
        "quality": overview.get("quality", {"score": 0, "status": "critical", "warnings": []}),
        "alerts": overview.get("alerts", [])[:6],
        "recent_events": recent_events,
        "current_week_events": overview.get("timetable", [])[:8],
        "classes": list(
            AcademicClass.objects.select_related("programme", "academic_year", "branch")
            .filter(is_active=True)
            .order_by("branch__name", "level")[:6]
        ),
        "sidebar_links": [
            {"label": "Vue generale", "href": "#overview"},
            {"label": "Support", "href": "#support"},
            {"label": "Sante", "href": "#health"},
            {"label": "Activite", "href": "#activity"},
        ],
        "support_actions": [
            "Reinitialiser un acces",
            "Verifier un dashboard",
            "Surveiller les alertes",
            "Contrôler les modules actifs",
        ],
    }
    return render(request, "portal/staff/informaticien_dashboard.html", context)
