from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch
from django.utils import timezone

from academics.models import AcademicClass, AcademicEnrollment, AcademicScheduleEvent, LessonLog
from academics.services.lesson_log_service import create_lesson_log, update_lesson_log
from academics.services.schedule_service import get_director_schedule_overview
from accounts.access import can_access, get_user_position, get_user_scope
from accounts.dashboards.helpers import get_user_branch
from branches.models import Branch
from portal.permissions import get_post_login_portal_url
from portal.services import build_it_dashboard_context, build_supervisor_dashboard_context
from portal.services.it_support_service import (
    can_manage_user_in_branch,
    create_temp_password,
    get_scoped_staff_queryset,
    log_support_action,
)
from students.models import Student
from students.services.attendance_service import mark_student_attendance, mark_teacher_attendance
from secretary.permissions import is_secretary


def _build_portal_context(request, *, page_title, module_cards):
    scope = get_user_scope(request.user)
    user_display_name = request.user.get_full_name() or request.user.username
    try:
        secretary_url = reverse("secretary:secretary_dashboard")
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


def _render_director_dashboard(request):
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


def _render_supervisor_dashboard(request):
    context = build_supervisor_dashboard_context(
        request,
        branch=_resolve_academic_branch(request),
        page_title="Dashboard Surveillant General",
        page_kicker="Surveillance generale",
        sidebar_links=[
            {"label": "Vue generale", "href": "#overview"},
            {"label": "Presences", "href": "#attendance"},
            {"label": "Cours", "href": "#courses"},
            {"label": "Classes", "href": "#classes"},
            {"label": "Alertes", "href": "#alerts"},
        ],
        highlight=[
            "Presence et retards",
            "Cours et cahier de texte",
            "Classes a surveiller",
            "Alertes terrain",
        ],
        base_context_builder=_build_portal_context,
    )
    return render(request, "portal/staff/supervisor_dashboard.html", context)


def _build_supervisor_dashboard_context_for_partials(request, *, branch):
    return build_supervisor_dashboard_context(
        request,
        branch=branch,
        page_title="Dashboard Surveillant General",
        page_kicker="Surveillance generale",
        sidebar_links=[
            {"label": "Vue generale", "href": "#overview"},
            {"label": "Presences", "href": "#attendance"},
            {"label": "Cours", "href": "#courses"},
            {"label": "Classes", "href": "#classes"},
            {"label": "Alertes", "href": "#alerts"},
        ],
        highlight=[
            "Presence et retards",
            "Cours et cahier de texte",
            "Classes a surveiller",
            "Alertes terrain",
        ],
        base_context_builder=_build_portal_context,
    )


def _render_it_dashboard(request):
    return render(
        request,
        "portal/staff/informaticien_dashboard.html",
        _build_it_dashboard_context(request),
    )


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
    if position in {"director_of_studies", "executive_director", "super_admin"}:
        return _render_director_dashboard(request)
    if position == "academic_supervisor":
        return _render_supervisor_dashboard(request)
    if position == "it_support":
        return _render_it_dashboard(request)

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
    return redirect("accounts_portal:portal_dashboard")


@_position_required({"secretary"})
def secretary_portal(request):
    return redirect("accounts_portal:portal_dashboard")


@_position_required({"admissions"})
def admissions_portal(request):
    return redirect("accounts_portal:portal_dashboard")


@_position_required({"director_of_studies", "executive_director", "super_admin"})
def director_portal(request):
    return redirect("accounts_portal:portal_dashboard")


@_position_required({"academic_supervisor"})
def supervisor_portal(request):
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
    return _redirect_it_dashboard(request)


@_position_required({"academic_supervisor"})
def supervisor_mark_student_attendance(request):
    if request.method != "POST":
        return _deny_portal_access(request)

    branch = _resolve_academic_branch(request)
    if branch is None:
        messages.error(request, "Aucune annexe n'est rattachee a ce compte.")
        if request.headers.get("HX-Request") == "true":
            context = _build_supervisor_dashboard_context_for_partials(request, branch=branch)
            context["toast"] = {"level": "error", "message": "Aucune annexe n'est rattachee a ce compte."}
            return render(request, "portal/staff/supervisor/partials/panel_attendance.html", context)
        return _redirect_supervisor_dashboard("attendance")

    try:
        schedule_event = (
            AcademicScheduleEvent.objects.select_related("academic_class", "teacher", "ec", "branch")
            .filter(
                pk=request.POST.get("schedule_event_id"),
                branch=branch,
                event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
                is_active=True,
            )
            .exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
            .get()
        )
        student = (
            Student.objects.select_related("user", "inscription__candidature")
            .filter(
                pk=request.POST.get("student_id"),
                inscription__candidature__branch=branch,
                user__academic_enrollments__academic_class=schedule_event.academic_class,
                user__academic_enrollments__branch=branch,
                user__academic_enrollments__is_active=True,
            )
            .distinct()
            .get()
        )
        result = mark_student_attendance(
            student=student,
            academic_class=schedule_event.academic_class,
            schedule_event=schedule_event,
            status=request.POST.get("status", ""),
            recorded_by=request.user,
            branch=branch,
            arrival_time=_parse_optional_time(request.POST.get("arrival_time")),
            justification=request.POST.get("justification", ""),
        )
    except (AcademicScheduleEvent.DoesNotExist, Student.DoesNotExist):
        messages.error(request, "Selection invalide pour la saisie de presence etudiant.")
        if request.headers.get("HX-Request") == "true":
            context = _build_supervisor_dashboard_context_for_partials(request, branch=branch)
            context["toast"] = {"level": "error", "message": "Selection invalide pour la saisie de presence etudiant."}
            return render(request, "portal/staff/supervisor/partials/panel_attendance.html", context)
        return _redirect_supervisor_dashboard("attendance")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        if request.headers.get("HX-Request") == "true":
            context = _build_supervisor_dashboard_context_for_partials(request, branch=branch)
            context["toast"] = {"level": "error", "message": " ".join(exc.messages)}
            return render(request, "portal/staff/supervisor/partials/panel_attendance.html", context)
        return _redirect_supervisor_dashboard("attendance")

    attendance = result["attendance"]
    messages.success(
        request,
        f"Presence etudiant enregistree: {attendance.student.full_name} - {attendance.get_status_display()}.",
    )
    if request.headers.get("HX-Request") == "true":
        context = _build_supervisor_dashboard_context_for_partials(request, branch=branch)
        context["toast"] = {
            "level": "success",
            "message": f"Presence etudiant enregistree: {attendance.student.full_name} - {attendance.get_status_display()}.",
        }
        return render(request, "portal/staff/supervisor/partials/panel_attendance.html", context)
    return _redirect_supervisor_dashboard("attendance")


@_position_required({"academic_supervisor"})
def supervisor_mark_teacher_attendance(request):
    if request.method != "POST":
        return _deny_portal_access(request)

    branch = _resolve_academic_branch(request)
    if branch is None:
        messages.error(request, "Aucune annexe n'est rattachee a ce compte.")
        if request.headers.get("HX-Request") == "true":
            context = _build_supervisor_dashboard_context_for_partials(request, branch=branch)
            context["toast"] = {"level": "error", "message": "Aucune annexe n'est rattachee a ce compte."}
            return render(request, "portal/staff/supervisor/partials/panel_attendance.html", context)
        return _redirect_supervisor_dashboard("attendance")

    try:
        schedule_event = (
            AcademicScheduleEvent.objects.select_related("academic_class", "teacher", "ec", "branch")
            .filter(
                pk=request.POST.get("schedule_event_id"),
                branch=branch,
                event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
                is_active=True,
            )
            .exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
            .get()
        )
        result = mark_teacher_attendance(
            teacher=schedule_event.teacher,
            schedule_event=schedule_event,
            status=request.POST.get("status", ""),
            recorded_by=request.user,
            branch=branch,
            arrival_time=_parse_optional_time(request.POST.get("arrival_time")),
            justification=request.POST.get("justification", ""),
        )
    except AcademicScheduleEvent.DoesNotExist:
        messages.error(request, "Cours introuvable pour la saisie de presence enseignant.")
        if request.headers.get("HX-Request") == "true":
            context = _build_supervisor_dashboard_context_for_partials(request, branch=branch)
            context["toast"] = {"level": "error", "message": "Cours introuvable pour la saisie de presence enseignant."}
            return render(request, "portal/staff/supervisor/partials/panel_attendance.html", context)
        return _redirect_supervisor_dashboard("attendance")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        if request.headers.get("HX-Request") == "true":
            context = _build_supervisor_dashboard_context_for_partials(request, branch=branch)
            context["toast"] = {"level": "error", "message": " ".join(exc.messages)}
            return render(request, "portal/staff/supervisor/partials/panel_attendance.html", context)
        return _redirect_supervisor_dashboard("attendance")

    attendance = result["attendance"]
    messages.success(
        request,
        f"Presence enseignant enregistree: {attendance.teacher.get_full_name() or attendance.teacher.username} - {attendance.get_status_display()}.",
    )
    if request.headers.get("HX-Request") == "true":
        context = _build_supervisor_dashboard_context_for_partials(request, branch=branch)
        context["toast"] = {
            "level": "success",
            "message": f"Presence enseignant enregistree: {attendance.teacher.get_full_name() or attendance.teacher.username} - {attendance.get_status_display()}.",
        }
        return render(request, "portal/staff/supervisor/partials/panel_attendance.html", context)
    return _redirect_supervisor_dashboard("attendance")


@_position_required({"academic_supervisor"})
def supervisor_save_lesson_log(request):
    if request.method != "POST":
        return _deny_portal_access(request)

    branch = _resolve_academic_branch(request)
    if branch is None:
        messages.error(request, "Aucune annexe n'est rattachee a ce compte.")
        if request.headers.get("HX-Request") == "true":
            context = _build_supervisor_dashboard_context_for_partials(request, branch=branch)
            context["toast"] = {"level": "error", "message": "Aucune annexe n'est rattachee a ce compte."}
            return render(request, "portal/staff/supervisor/partials/panel_courses.html", context)
        return _redirect_supervisor_dashboard("courses")

    try:
        schedule_event = (
            AcademicScheduleEvent.objects.select_related("academic_class", "teacher", "ec", "branch")
            .filter(
                pk=request.POST.get("schedule_event_id"),
                branch=branch,
                event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
                is_active=True,
            )
            .exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
            .get()
        )
        lesson_log = (
            LessonLog.objects.select_related("academic_class", "teacher", "ec", "branch", "schedule_event")
            .filter(branch=branch, schedule_event=schedule_event, date=timezone.localdate(schedule_event.start_datetime))
            .first()
        )
        lesson_log_kwargs = {
            "status": request.POST.get("status", ""),
            "content": request.POST.get("content", ""),
            "homework": request.POST.get("homework", ""),
            "observations": request.POST.get("observations", ""),
        }
        if lesson_log is None:
            lesson_log = create_lesson_log(
                academic_class=schedule_event.academic_class,
                ec=schedule_event.ec,
                teacher=schedule_event.teacher,
                date=timezone.localdate(schedule_event.start_datetime),
                start_time=timezone.localtime(schedule_event.start_datetime).time(),
                end_time=timezone.localtime(schedule_event.end_datetime).time(),
                branch=branch,
                created_by=request.user,
                schedule_event=schedule_event,
                **lesson_log_kwargs,
            )
        else:
            lesson_log = update_lesson_log(
                lesson_log,
                updated_by=request.user,
                **lesson_log_kwargs,
            )
    except AcademicScheduleEvent.DoesNotExist:
        messages.error(request, "Cours introuvable pour le cahier de texte.")
        if request.headers.get("HX-Request") == "true":
            context = _build_supervisor_dashboard_context_for_partials(request, branch=branch)
            context["toast"] = {"level": "error", "message": "Cours introuvable pour le cahier de texte."}
            return render(request, "portal/staff/supervisor/partials/panel_courses.html", context)
        return _redirect_supervisor_dashboard("courses")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        if request.headers.get("HX-Request") == "true":
            context = _build_supervisor_dashboard_context_for_partials(request, branch=branch)
            context["toast"] = {"level": "error", "message": " ".join(exc.messages)}
            return render(request, "portal/staff/supervisor/partials/panel_courses.html", context)
        return _redirect_supervisor_dashboard("courses")

    messages.success(
        request,
        f"Cahier de texte enregistre pour {lesson_log.academic_class.display_name} - {lesson_log.ec.title}.",
    )
    if request.headers.get("HX-Request") == "true":
        context = _build_supervisor_dashboard_context_for_partials(request, branch=branch)
        context["toast"] = {
            "level": "success",
            "message": f"Cahier de texte enregistre pour {lesson_log.academic_class.display_name} - {lesson_log.ec.title}.",
        }
        return render(request, "portal/staff/supervisor/partials/panel_courses.html", context)
    return _redirect_supervisor_dashboard("courses")


from django.contrib.auth.decorators import login_required
from accounts.access import get_user_position
from django.http import HttpResponseForbidden
from django.shortcuts import render


@_position_required({"academic_supervisor"})
def supervisor_quick_search(request):
    branch = _resolve_academic_branch(request)
    if branch is None:
        return render(
            request,
            "portal/staff/supervisor/partials/search_results.html",
            {"query": "", "students": [], "classes": [], "events": []},
        )

    query = (request.GET.get("q") or "").strip()
    if len(query) < 2:
        return render(
            request,
            "portal/staff/supervisor/partials/search_results.html",
            {"query": query, "students": [], "classes": [], "events": []},
        )

    from django.db.models import Q

    from academics.models import AcademicClass, AcademicScheduleEvent
    from students.models import Student

    students = list(
        Student.objects.select_related("user", "inscription__candidature")
        .filter(
            Q(matricule__icontains=query)
            | Q(inscription__candidature__last_name__icontains=query)
            | Q(inscription__candidature__first_name__icontains=query),
            inscription__candidature__branch=branch,
            is_active=True,
        )
        .order_by("inscription__candidature__last_name", "inscription__candidature__first_name", "matricule")[:6]
    )

    classes = list(
        AcademicClass.objects.select_related("programme", "academic_year", "branch")
        .filter(
            branch=branch,
            is_active=True,
        )
        .filter(
            Q(display_name__icontains=query)
            | Q(programme__title__icontains=query)
            | Q(level__icontains=query)
        )
        .order_by("level", "programme__title")[:6]
    )

    today = timezone.localdate()
    events = list(
        AcademicScheduleEvent.objects.select_related("academic_class", "teacher", "ec", "branch")
        .filter(
            branch=branch,
            start_datetime__date=today,
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            is_active=True,
        )
        .filter(
            Q(academic_class__display_name__icontains=query)
            | Q(teacher__first_name__icontains=query)
            | Q(teacher__last_name__icontains=query)
            | Q(ec__title__icontains=query)
            | Q(location__icontains=query)
        )
        .order_by("start_datetime")[:6]
    )

    return render(
        request,
        "portal/staff/supervisor/partials/search_results.html",
        {"query": query, "students": students, "classes": classes, "events": events},
    )


@_position_required({"academic_supervisor"})
def supervisor_student_options(request):
    branch = _resolve_academic_branch(request)
    query = (request.GET.get("q") or "").strip()
    if branch is None or len(query) < 2:
        return render(
            request,
            "portal/staff/supervisor/partials/student_options.html",
            {"items": []},
        )

    from django.db.models import Q

    from students.models import Student

    students = (
        Student.objects.select_related("user", "inscription__candidature")
        .filter(
            Q(matricule__icontains=query)
            | Q(inscription__candidature__last_name__icontains=query)
            | Q(inscription__candidature__first_name__icontains=query),
            inscription__candidature__branch=branch,
            is_active=True,
        )
        .order_by("inscription__candidature__last_name", "inscription__candidature__first_name", "matricule")[:30]
    )
    items = [{"id": student.id, "label": f"{student.full_name} - {student.matricule}"} for student in students]
    return render(
        request,
        "portal/staff/supervisor/partials/student_options.html",
        {"items": items},
    )


def _build_supervisor_class_detail_context(request, *, branch, class_id: int, week_start):
    from django.contrib.auth import get_user_model
    from django.db.models import Count, Q

    from academics.models import AcademicClass, EC
    from academics.services.schedule_service import get_class_week_schedule
    from students.models import Student

    User = get_user_model()

    academic_class = (
        AcademicClass.objects.select_related("programme", "academic_year", "branch")
        .annotate(student_count=Count("enrollments"))
        .filter(branch=branch, is_active=True)
        .get(pk=class_id)
    )

    schedule = get_class_week_schedule(academic_class, week_start)
    prev_week_start = schedule["week_start"] - timedelta(days=7)
    next_week_start = schedule["week_start"] + timedelta(days=7)

    students = list(
        Student.objects.select_related("user", "inscription__candidature")
        .filter(
            inscription__candidature__branch=branch,
            is_active=True,
            user__academic_enrollments__academic_class=academic_class,
            user__academic_enrollments__is_active=True,
        )
        .distinct()
        .order_by("inscription__candidature__last_name", "inscription__candidature__first_name", "matricule")[:200]
    )

    ecs = list(
        EC.objects.select_related("ue", "ue__semester")
        .filter(ue__semester__academic_class=academic_class)
        .order_by("ue__semester__order", "ue__code", "title")[:250]
    )

    teacher_q = (request.GET.get("teacher_q") or "").strip()
    teachers_qs = User.objects.filter(is_active=True)
    if teacher_q:
        teachers_qs = teachers_qs.filter(
            Q(first_name__icontains=teacher_q)
            | Q(last_name__icontains=teacher_q)
            | Q(username__icontains=teacher_q)
        )
    teachers = list(teachers_qs.order_by("first_name", "last_name", "username")[:80])

    return {
        "branch": branch,
        "academic_class": academic_class,
        "students": students,
        "schedule": schedule,
        "prev_week_start": prev_week_start,
        "next_week_start": next_week_start,
        "ecs": ecs,
        "teachers": teachers,
    }


@_position_required({"academic_supervisor"})
def supervisor_class_detail(request, class_id: int):
    branch = _resolve_academic_branch(request)
    if branch is None:
        return render(
            request,
            "portal/staff/supervisor/partials/class_detail.html",
            {"toast": {"level": "error", "message": "Aucune annexe n'est rattachee a ce compte."}},
        )

    week_start_raw = (request.GET.get("week_start") or "").strip()
    week_start = timezone.localdate()
    if week_start_raw:
        try:
            week_start = datetime.strptime(week_start_raw, "%Y-%m-%d").date()
        except ValueError:
            week_start = timezone.localdate()

    context = _build_supervisor_class_detail_context(
        request,
        branch=branch,
        class_id=class_id,
        week_start=week_start,
    )
    return render(
        request,
        "portal/staff/supervisor/partials/class_detail.html",
        context,
    )


@_position_required({"academic_supervisor"})
def supervisor_create_schedule_event(request, class_id: int):
    if request.method != "POST":
        return _deny_portal_access(request)

    branch = _resolve_academic_branch(request)
    if branch is None:
        return _deny_portal_access(request)

    from django.contrib.auth import get_user_model
    from django.core.exceptions import ValidationError

    from academics.models import AcademicClass, AcademicYear, AcademicScheduleEvent, EC
    from academics.services.schedule_service import create_schedule_event

    User = get_user_model()
    academic_class = AcademicClass.objects.select_related("academic_year", "branch").get(
        pk=class_id,
        branch=branch,
        is_active=True,
    )
    ec = EC.objects.select_related("ue", "ue__semester").get(pk=request.POST.get("ec_id"))
    teacher = User.objects.get(pk=request.POST.get("teacher_id"))

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
            title="",
            description="",
            start_datetime=start_dt,
            end_datetime=end_dt,
            location=location,
            is_online=is_online,
            is_active=True,
        )
        toast = {"level": "success", "message": "Cours programme sur la semaine."}
    except (ValidationError, EC.DoesNotExist, User.DoesNotExist) as exc:
        msg = " ".join(getattr(exc, "messages", [])) if hasattr(exc, "messages") else str(exc)
        toast = {"level": "error", "message": msg or "Impossible de programmer ce cours."}

    week_start_raw = (request.POST.get("week_start") or "").strip()
    week_start = timezone.localdate()
    if week_start_raw:
        try:
            week_start = datetime.strptime(week_start_raw, "%Y-%m-%d").date()
        except ValueError:
            week_start = timezone.localdate()
    context = _build_supervisor_class_detail_context(
        request,
        branch=branch,
        class_id=class_id,
        week_start=week_start,
    )
    context["toast"] = toast
    return render(request, "portal/staff/supervisor/partials/class_detail.html", context)

@login_required
def dg_portal(request):
    position = get_user_position(request.user)
    if position not in {"executive_director", "super_admin"}:
        return HttpResponseForbidden("Accès réservé au Directeur Général.")
    return render(request, "portal/dg/dashboard.html", {
        "page_title": "Dashboard Directeur Général",
        "user_display_name": request.user.get_full_name() or request.user.username,
    })
