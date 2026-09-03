import json
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.forms import SystemProfileForm, UserPreferenceForm
from accounts.models import Profile, UserPreference
from core.models import SignatureRequest
from core.services.signatures import approve_signature, get_signed_signature_for_subject

from academics.models import AcademicClass, AcademicScheduleEvent, EC, LessonLog, WeeklyScheduleSlot
from academics.services.lesson_log_service import create_lesson_log, update_lesson_log
from academics.services.schedule_service import (
    create_schedule_event,
    create_weekly_schedule_slot,
    deactivate_weekly_schedule_slot,
    materialize_week_events_from_weekly_slots,
    update_weekly_schedule_slot,
)
from academics.services.session_service import assign_session_replacement
from students.models import (
    AttendanceAlert,
    AttendanceRollSheet,
    Convocation,
    Student,
    StudentAttendance,
    StudentCase,
    TeacherAttendance,
    TeacherCase,
)
from students.services.attendance_service import (
    get_student_attendance_history,
    list_students_for_schedule_event,
    mark_student_attendance,
    mark_teacher_attendance,
)
from students.services.attendance_workflow import (
    assert_roll_allows_editing,
    is_roll_locked_for_event,
    reopen_daily_roll,
    start_daily_roll,
    touch_roll_after_bulk_save,
    validate_daily_roll,
)
from students.services.case_service import advance_teacher_case, count_open_cases, create_teacher_case
from students.services.convocation_service import create_convocation
from portal.services.certified_dashboard_shell import build_certified_dashboard_shell
from portal.services.supervisor_dashboard_service import get_supervisor_class_picker_bundle
from portal.services.supervisor_dashboard_presentation import (
    build_supervisor_dashboard_presentation,
)
from portal.services.supervisor_workspace_service import (
    SECTION_META as SUPERVISOR_SECTION_META,
    build_supervisor_workspace_context,
    resolve_section_view,
)
from portal.services.supervisor_service import (
    build_attendance_monthly_report_context,
    build_attendance_section_context,
    build_class_detail_context,
    build_courses_section_context,
    build_home_section_context,
    build_schedule_section_context,
    build_students_section_context,
    build_teachers_section_context,
    build_teachers_weekly_report_context,
    next_attendance_status,
)
from portal.services.teacher_dashboard_service import build_lesson_log_signature_snapshot
from portal.views.views import (
    _build_portal_context,
    _build_weekly_slots_workspace_context,
    _deny_portal_access,
    _inject_planner_route_context,
    _materialize_period_from_weekly_slots,
    _parse_optional_time,
    _parse_slot_time_hhmm,
    _position_required,
    _resolve_director_branch,
    _user_initials,
)


def _resolve_supervisor_branch(request):
    """Return the mandatory annexe for every supervisor workflow."""

    return _resolve_director_branch(
        request,
        additional_scoped_positions={"academic_supervisor"},
    )


def _redirect_supervisor_dashboard(section="home"):
    section = {
        "overview": "home",
        "absences": "attendance",
    }.get(section, section)
    base_url = reverse("accounts_portal:portal_dashboard")
    return redirect(f"{base_url}?section={section}")


def _removed_supervisor_capability():
    return HttpResponseForbidden(
        "Cette action relève désormais du Directeur des études. "
        "Le Surveillant général dispose d'un accès de consultation uniquement."
    )


_SECTION_META = SUPERVISOR_SECTION_META


def _supervisor_account_context(request):
    profile, _created = Profile.objects.get_or_create(user=request.user)
    position_label = dict(Profile.POSITION_CHOICES).get(
        profile.position,
        profile.position or "Surveillant général",
    )
    status_label = dict(Profile.EMPLOYMENT_STATUS_CHOICES).get(
        profile.employment_status,
        profile.employment_status or "Actif",
    )
    panel_url = reverse("accounts_portal:supervisor_account_panel")
    actions = [
        {"label": "Modifier", "icon": "pencil", "hx_get": f"{panel_url}?view=edit", "hx_target": "#supervisor-drawer-content", "hx_swap": "innerHTML"},
        {"label": "Sécurité", "icon": "shield", "hx_get": f"{panel_url}?view=security", "hx_target": "#supervisor-drawer-content", "hx_swap": "innerHTML"},
        {"label": "Préférences", "icon": "settings", "hx_get": f"{panel_url}?view=preferences", "hx_target": "#supervisor-drawer-content", "hx_swap": "innerHTML"},
    ]
    return {
        "profile": profile,
        "account_display_name": request.user.get_full_name() or request.user.username,
        "account_avatar_url": profile.avatar_url,
        "account_role": position_label or "Surveillant général",
        "email": request.user.email,
        "branch_label": profile.branch.name if profile.branch else "Annexe non définie",
        "status": profile.employment_status,
        "status_label": status_label,
        "phone": profile.phone,
        "address": profile.address,
        "created_at": timezone.localtime(profile.created_at).strftime("%d/%m/%Y") if profile.created_at else "",
        "last_seen": timezone.localtime(profile.last_seen).strftime("%d/%m/%Y %H:%M") if profile.last_seen else "",
        "bio": profile.bio,
        "account_actions": actions,
    }


def _render_supervisor_dashboard(request, *, section=None):
    branch = _resolve_supervisor_branch(request)
    workspace_context = build_supervisor_workspace_context(
        request,
        branch=branch,
        section=section,
    )
    workspace_context["open_cases_count"] = count_open_cases(branch=branch)
    context = {
        **_build_portal_context(
            request,
            page_title="Dashboard Surveillant General",
            module_cards=["Suivi des classes", "Assiduite", "Emploi du temps"],
        ),
        **workspace_context,
    }
    display_name = (
        context.get("user_display_name")
        or request.user.get_full_name()
        or getattr(request.user, "username", "")
        or ""
    )
    context["user_initials"] = _user_initials(display_name)
    context["active_alerts_count"] = len(context.get("alerts") or [])
    context.update(_supervisor_account_context(request))
    presentation = build_supervisor_dashboard_presentation(request, context)
    context.update(presentation)
    context.update(
        build_certified_dashboard_shell(
            role="academic_supervisor",
            key="supervisor",
            page_title=context["page_title"],
            title="Surveillance générale",
            subtitle="Surveillance générale",
            context_label=context.get("supervisor_context_label") or "",
            user_name=context.get("user_display_name") or display_name,
            navigation=context.get("supervisor_navigation") or [],
            active_section=context.get("supervisor_active_section") or "home",
            workspace_template="portal/staff/supervisor/partials/workflow_workspace.html",
            topbar_template="portal/staff/supervisor/partials/topbar_actions.html",
            script_path="src/js/portal/supervisor_dashboard.js",
            notifications_url=context.get("notifications_url") or "",
            show_notifications_button=False,
            drawer_title="Détail",
            modal_title="Supervision",
            empty_modal_message="Le contenu de cette fenêtre sera chargé à la demande.",
        )
    )
    return render(request, "portal/staff/director_dashboard.html", context)


def _parse_supervisor_section(request, default="home"):
    section, _ = resolve_section_view(request, section=None)
    return section or default


def _parse_workflow_roll_date(request):
    raw = (request.GET.get("roll_date") or request.POST.get("roll_date") or "").strip()
    if not raw:
        return timezone.localdate()
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return timezone.localdate()


def _parse_supervisor_planner_request(request):
    branch = _resolve_supervisor_branch(request)
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


# Section dispatch for the workflow workspace. Each builder returns a dict of
# context updates; the request/branch/class are already validated by the caller.
_SECTION_BUILDERS = {
    "schedule": lambda request, branch, academic_class, week_start: build_schedule_section_context(
        branch=branch, academic_class=academic_class, week_start=week_start
    ),
    "courses": lambda request, branch, academic_class, week_start: build_courses_section_context(
        request=request, branch=branch, academic_class=academic_class
    ),
    "attendance": lambda request, branch, academic_class, week_start: build_attendance_section_context(
        request=request,
        branch=branch,
        academic_class=academic_class,
        roll_date=_parse_workflow_roll_date(request),
    ),
    "students": lambda request, branch, academic_class, week_start: build_students_section_context(
        request=request, branch=branch, academic_class=academic_class
    ),
}


def _render_legacy_supervisor_workflow_workspace(request, *, section=None, toast=None):
    # This view always renders the HTMX panel only; the full-page shell is
    # rendered separately by _render_supervisor_dashboard (via portal_dashboard).
    branch = _resolve_supervisor_branch(request)
    resolved_section = section or _parse_supervisor_section(request)
    _, class_picker_items, _ = get_supervisor_class_picker_bundle(branch=branch)

    selected_class_id = None
    selected_class_raw = (request.GET.get("class_id") or request.POST.get("class_id") or "").strip()
    if selected_class_raw.isdigit():
        selected_class_id = int(selected_class_raw)

    selected_class = None
    if branch and selected_class_id:
        selected_class = (
            AcademicClass.objects.select_related("programme", "academic_year", "branch")
            .annotate(student_count=Count("enrollments", filter=Q(enrollments__is_active=True)))
            .filter(branch=branch, is_active=True, pk=selected_class_id)
            .first()
        )

    open_cases_count = count_open_cases(branch=branch) if branch else 0
    crumb, panel_title, panel_lede = _SECTION_META.get(resolved_section, _SECTION_META["home"])

    context = {
        "branch": branch,
        "section": resolved_section,
        "crumb": crumb,
        "panel_title": panel_title,
        "panel_lede": panel_lede,
        "today": timezone.localdate(),
        "class_picker_items": class_picker_items,
        "open_cases_count": open_cases_count,
        "selected_class": selected_class,
        "selected_class_id": selected_class.id if selected_class else None,
        "selected_class_label": selected_class.display_name if selected_class else "",
        "supervisor_dashboard_base_url": reverse("accounts_portal:portal_dashboard"),
        "high_absence_classes": [],
        "schedule_conflicts": [],
        "unfollowed_classes": [],
    }
    if toast:
        context["toast"] = toast

    if branch is None:
        return render(request, "portal/staff/supervisor/partials/workflow_workspace.html", context)

    if resolved_section == "teachers":
        # Section transverse a l'annexe, independante de la classe selectionnee.
        context.update(build_teachers_section_context(branch=branch))
        return render(request, "portal/staff/supervisor/partials/workflow_workspace.html", context)

    if resolved_section == "teachers_report":
        week_start_raw = (request.GET.get("week_start") or "").strip()
        week_start = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
        if week_start_raw:
            try:
                week_start = datetime.strptime(week_start_raw, "%Y-%m-%d").date()
            except ValueError:
                pass
        context.update(build_teachers_weekly_report_context(branch=branch, week_start=week_start))
        return render(request, "portal/staff/supervisor/partials/workflow_workspace.html", context)

    if resolved_section == "attendance_report":
        if selected_class is None:
            return render(request, "portal/staff/supervisor/partials/workflow_workspace.html", context)
        month_raw = (request.GET.get("month") or "").strip()
        today = timezone.localdate()
        try:
            report_month = datetime.strptime(month_raw, "%Y-%m").date().replace(day=1) if month_raw else today.replace(day=1)
        except ValueError:
            report_month = today.replace(day=1)
        context.update(build_attendance_monthly_report_context(branch=branch, academic_class=selected_class, month=report_month))
        return render(request, "portal/staff/supervisor/partials/workflow_workspace.html", context)

    if resolved_section == "home":
        context.update(build_home_section_context(branch=branch, selected_class=selected_class))
        return render(request, "portal/staff/supervisor/partials/workflow_workspace.html", context)

    if selected_class is None:
        # Verrouillage strict : pas de classe => on renvoie le workspace qui affichera uniquement le picker
        return render(request, "portal/staff/supervisor/partials/workflow_workspace.html", context)

    week_start = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
    week_start_raw = (request.GET.get("week_start") or request.POST.get("week_start") or "").strip()
    if week_start_raw:
        try:
            week_start = datetime.strptime(week_start_raw, "%Y-%m-%d").date()
        except ValueError:
            pass

    builder = _SECTION_BUILDERS.get(resolved_section)
    if builder:
        context.update(builder(request, branch, selected_class, week_start))

    if resolved_section == "schedule":
        context["academic_class"] = selected_class
        _inject_planner_route_context(context, role_prefix="supervisor", workspace_target_id="#supervisor-workspace")

    return render(request, "portal/staff/supervisor/partials/workflow_workspace.html", context)


def _render_supervisor_workflow_workspace(
    request,
    *,
    section=None,
    toast=None,
    force_subcontent=False,
):
    """Render the common workspace shell or one of its HTMX subwindows."""

    branch = _resolve_supervisor_branch(request)
    context = build_supervisor_workspace_context(
        request,
        branch=branch,
        section=section,
        toast=toast,
    )
    context.update(build_supervisor_dashboard_presentation(request, context))
    is_subcontent = force_subcontent or request.GET.get("fragment") == "subcontent"
    template_name = (
        "portal/staff/supervisor/partials/subcontent.html"
        if is_subcontent
        else "portal/staff/supervisor/partials/workflow_workspace.html"
    )
    return render(request, template_name, context)


@_position_required({"academic_supervisor"})
def supervisor_workflow_workspace(request):
    # Requete HTMX (navigation interne) -> panneau seul.
    # Une requete complete revient toujours vers l'entree Portal canonique.
    if request.htmx:
        return _render_supervisor_workflow_workspace(request)
    params = request.GET.copy()
    section, active_view = resolve_section_view(request)
    params["section"] = section
    params["view"] = active_view
    params.pop("fragment", None)
    return redirect(
        f"{reverse('accounts_portal:portal_dashboard')}?{params.urlencode()}"
    )


@_position_required({"academic_supervisor"})
def supervisor_attendance_toggle_student(request):
    if request.method != "POST":
        return _deny_portal_access(request)

    branch = _resolve_supervisor_branch(request)
    if branch is None:
        return HttpResponseBadRequest("Aucune annexe rattachee.")

    raw_status = (request.POST.get("status") or "").strip()
    if raw_status not in {StudentAttendance.STATUS_PRESENT, StudentAttendance.STATUS_ABSENT, StudentAttendance.STATUS_LATE}:
        return HttpResponseBadRequest("Statut invalide.")

    try:
        schedule_event = (
            AcademicScheduleEvent.objects.select_related("academic_class", "teacher", "ec", "branch")
            .filter(
                pk=request.POST.get("schedule_event_id"),
                branch=branch,
                event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
                is_active=True,
            )
            .exclude(
                status__in={
                    AcademicScheduleEvent.STATUS_DRAFT,
                    AcademicScheduleEvent.STATUS_CANCELLED,
                }
            )
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
        roll_date = timezone.localtime(schedule_event.start_datetime).date()
        if roll_date > timezone.localdate():
            raise ValidationError("La présence étudiante ne peut être saisie avant le jour de la séance.")
        assert_roll_allows_editing(
            branch=branch,
            academic_class_id=schedule_event.academic_class_id,
            roll_date=roll_date,
            schedule_event_id=schedule_event.pk,
        )
        result = mark_student_attendance(
            student=student,
            academic_class=schedule_event.academic_class,
            schedule_event=schedule_event,
            status=raw_status,
            recorded_by=request.user,
            branch=branch,
            arrival_time=(
                _parse_optional_time(request.POST.get("arrival_time"))
                if raw_status == StudentAttendance.STATUS_LATE
                else None
            ),
            justification=(request.POST.get("justification") or "").strip(),
            is_justified=(
                raw_status == StudentAttendance.STATUS_ABSENT
                and (request.POST.get("is_justified") or "").lower() in {"1", "true", "on", "yes"}
            ),
            observation=(request.POST.get("observation") or "").strip(),
        )
        touch_roll_after_bulk_save(
            user=request.user,
            branch=branch,
            academic_class=schedule_event.academic_class,
            roll_date=roll_date,
            schedule_event=schedule_event,
        )
    except (AcademicScheduleEvent.DoesNotExist, Student.DoesNotExist):
        return HttpResponseBadRequest("Selection invalide.")
    except ValidationError as exc:
        return HttpResponseBadRequest(" ".join(exc.messages))

    attendance = result["attendance"]
    next_status = next_attendance_status(attendance.status)
    return render(
        request,
        "portal/staff/supervisor/partials/attendance_student_row.html",
        {
            "row": {
                "student": student,
                "status": attendance.status,
                "next_status": next_status,
                "arrival_time": attendance.arrival_time,
                "justification": attendance.justification,
                "is_justified": attendance.is_justified,
                "observation": attendance.observation,
            },
            "selected_event": schedule_event,
            "roll_locked": is_roll_locked_for_event(branch=branch, event=schedule_event),
        },
    )


@_position_required({"academic_supervisor"})
def supervisor_workflow_roll_action(request):
    if request.method != "POST":
        return _deny_portal_access(request)

    branch = _resolve_supervisor_branch(request)
    toast = None
    if branch is None:
        toast = {"level": "error", "message": "Aucune annexe n'est rattachee a ce compte."}
    else:
        action = (request.POST.get("action") or "").strip()
        try:
            if action == "start":
                class_id = int(request.POST.get("class_id") or 0)
                roll_date = datetime.strptime((request.POST.get("roll_date") or "").strip(), "%Y-%m-%d").date()
                raw_ev = (request.POST.get("schedule_event_id") or "").strip()
                if not raw_ev.isdigit():
                    raise ValidationError("Une séance publiée est obligatoire pour ouvrir l'appel.")
                schedule_event = AcademicScheduleEvent.objects.filter(
                    pk=int(raw_ev),
                    branch=branch,
                    academic_class_id=class_id,
                    event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
                    is_active=True,
                ).exclude(
                    status__in={
                        AcademicScheduleEvent.STATUS_DRAFT,
                        AcademicScheduleEvent.STATUS_CANCELLED,
                    }
                ).first()
                if schedule_event is None:
                    raise ValidationError("La séance publiée est introuvable dans votre annexe.")
                event_date = timezone.localtime(schedule_event.start_datetime).date()
                if roll_date != event_date:
                    raise ValidationError("La date de l'appel doit correspondre à la séance.")
                if roll_date > timezone.localdate():
                    raise ValidationError("L'appel ne peut être ouvert avant le jour de la séance.")
                start_daily_roll(
                    user=request.user,
                    branch=branch,
                    academic_class_id=class_id,
                    roll_date=roll_date,
                    schedule_event_id=schedule_event.pk,
                )
                toast = {"level": "success", "message": "Appel ouvert pour la seance."}
            elif action == "validate":
                sheet_id = int(request.POST.get("sheet_id") or 0)
                sheet = AttendanceRollSheet.objects.get(pk=sheet_id, branch=branch)
                validate_daily_roll(user=request.user, sheet=sheet)
                toast = {"level": "success", "message": "Appel enregistre et valide."}
            elif action == "reopen":
                return _removed_supervisor_capability()
            else:
                raise ValidationError("Action inconnue.")
        except AttendanceRollSheet.DoesNotExist:
            toast = {"level": "error", "message": "Feuille d'appel introuvable."}
        except (TypeError, ValueError) as exc:
            toast = {"level": "error", "message": str(exc) or "Donnees invalides."}
        except ValidationError as exc:
            toast = {"level": "error", "message": " ".join(exc.messages)}

    return _render_supervisor_workflow_workspace(
        request,
        section="attendance",
        toast=toast,
        force_subcontent=True,
    )


@_position_required({"academic_supervisor"})
def supervisor_quick_course_create(request):
    return _removed_supervisor_capability()

    branch = _resolve_supervisor_branch(request)
    if request.method == "GET":
        class_id_raw = (request.GET.get("class_id") or "").strip()
        if branch is None or not class_id_raw.isdigit():
            return render(
                request,
                "portal/staff/supervisor/partials/planner_course_form_drawer.html",
                {"academic_class": None},
            )
        week_start = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
        try:
            context = build_class_detail_context(
                request,
                branch=branch,
                class_id=int(class_id_raw),
                week_start=week_start,
            )
        except AcademicClass.DoesNotExist:
            context = {"academic_class": None}
        if context.get("academic_class"):
            context.update(build_courses_section_context(
                request=request,
                branch=branch,
                academic_class=context["academic_class"],
            ))
            _inject_planner_route_context(context, role_prefix="supervisor", workspace_target_id="#supervisor-workspace")
        response = render(request, "portal/staff/supervisor/partials/planner_course_form_drawer.html", context)
        response["HX-Trigger"] = "supervisor-drawer-open"
        return response
    if request.method != "POST":
        return _deny_portal_access(request)

    if branch is None:
        return _render_supervisor_workflow_workspace(
            request,
            section="courses",
            toast={"level": "error", "message": "Aucune annexe n'est rattachee a ce compte."},
        )

    User = get_user_model()
    target_section = (_parse_supervisor_section(request, default="courses") or "courses")

    try:
        class_id = int(request.POST.get("class_id") or 0)
        academic_class = AcademicClass.objects.select_related("academic_year", "branch").get(
            pk=class_id,
            branch=branch,
            is_active=True,
        )
        ec = EC.objects.select_related("ue", "ue__semester").get(
            pk=request.POST.get("ec_id"),
            ue__semester__academic_class=academic_class,
        )
        teacher = User.objects.get(
            pk=request.POST.get("teacher_id"),
            is_active=True,
            profile__branch=branch,
            profile__position="teacher",
        )
        date_value = (request.POST.get("date") or timezone.localdate().isoformat()).strip()
        start_time = (request.POST.get("start_time") or "").strip()
        end_time = (request.POST.get("end_time") or "").strip()
        if not (date_value and start_time and end_time):
            raise ValidationError("Date, heure debut et heure fin sont obligatoires.")
        start_dt = timezone.make_aware(datetime.strptime(f"{date_value} {start_time}", "%Y-%m-%d %H:%M"))
        end_dt = timezone.make_aware(datetime.strptime(f"{date_value} {end_time}", "%Y-%m-%d %H:%M"))
        if end_dt <= start_dt:
            raise ValidationError("L'heure de fin doit etre apres l'heure de debut.")

        course_title = f"{ec.title} - {academic_class.display_name}"
        create_schedule_event(
            user=request.user,
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            status=AcademicScheduleEvent.STATUS_PLANNED,
            academic_class=academic_class,
            academic_year=academic_class.academic_year,
            branch=branch,
            ec=ec,
            teacher=teacher,
            title=course_title,
            description="",
            start_datetime=start_dt,
            end_datetime=end_dt,
            location=(request.POST.get("location") or "").strip(),
            is_online=False,
            is_active=True,
        )
        toast = {"level": "success", "message": "Cours ajoute a l'emploi du temps."}
    except (
        ValueError,
        ValidationError,
        AcademicClass.DoesNotExist,
        EC.DoesNotExist,
        User.DoesNotExist,
    ) as exc:
        if hasattr(exc, "message_dict"):
            message = " ".join(
                message
                for messages in exc.message_dict.values()
                for message in messages
            )
        else:
            message = " ".join(getattr(exc, "messages", [])) if hasattr(exc, "messages") else str(exc)
        toast = {"level": "error", "message": message or "Impossible d'ajouter le cours."}

    return _render_supervisor_workflow_workspace(request, section=target_section, toast=toast)


@_position_required({"academic_supervisor"})
def supervisor_student_drawer(request):
    branch = _resolve_supervisor_branch(request)
    student_raw = (request.GET.get("student_id") or "").strip()
    enrollment_raw = (request.GET.get("enrollment_id") or "").strip()
    class_raw = (request.GET.get("class_id") or "").strip()
    if branch is None or (not student_raw.isdigit() and not enrollment_raw.isdigit()):
        return render(
            request,
            "portal/staff/supervisor/partials/student_drawer.html",
            {"student": None},
        )

    student_filters = {
        "inscription__candidature__branch": branch,
        "is_active": True,
    }
    if student_raw.isdigit():
        student_filters["pk"] = int(student_raw)

    student_qs = Student.objects.select_related("inscription__candidature", "user").filter(**student_filters)
    if class_raw.isdigit():
        student_qs = student_qs.filter(
            user__academic_enrollments__academic_class_id=int(class_raw),
            user__academic_enrollments__branch=branch,
            user__academic_enrollments__is_active=True,
        )
    if enrollment_raw.isdigit():
        student_qs = student_qs.filter(
            user__academic_enrollments__pk=int(enrollment_raw),
            user__academic_enrollments__branch=branch,
            user__academic_enrollments__is_active=True,
        )

    student = student_qs.distinct().first()
    if student is None and student_raw.isdigit():
        student = (
            Student.objects.select_related("inscription__candidature", "user")
            .filter(
                pk=int(student_raw),
                inscription__candidature__branch=branch,
                is_active=True,
            )
            .first()
        )
    history = get_student_attendance_history(student, branch=branch, limit=8) if student else []
    active_alerts = (
        AttendanceAlert.objects.filter(student=student, branch=branch, is_resolved=False).order_by("-triggered_at")
        if student
        else []
    )
    response = render(
        request,
        "portal/staff/supervisor/partials/student_drawer.html",
        {
            "student": student,
            "attendance_history": history,
            "active_alerts": active_alerts,
        },
    )
    response["HX-Trigger"] = "supervisor-drawer-open"
    return response


@_position_required({"academic_supervisor"})
def supervisor_portal(request):
    return redirect("accounts_portal:portal_dashboard")


@_position_required({"academic_supervisor"})
def supervisor_account_panel(request):
    """Shared account components inside the supervisor's common drawer."""
    view_name = (request.GET.get("view") or request.POST.get("view") or "profile").strip().lower()
    if view_name not in {"profile", "edit", "security", "preferences"}:
        return HttpResponseBadRequest("Vue de compte inconnue.")

    profile, _created = Profile.objects.get_or_create(user=request.user)
    preference, _created = UserPreference.objects.get_or_create(user=request.user)
    if request.method == "POST":
        if view_name == "edit":
            form = SystemProfileForm(request.POST, request.FILES, instance=profile, user=request.user)
            if form.is_valid():
                form.save()
                response = render(
                    request,
                    "portal/staff/supervisor/partials/account/profile.html",
                    _supervisor_account_context(request),
                )
                response["HX-Trigger"] = json.dumps({"ui:toast": {"message": "Profil mis à jour.", "tone": "success"}})
                return response
            return render(
                request,
                "portal/staff/supervisor/partials/account/edit.html",
                {"form": form, "profile": profile},
                status=400,
            )
        if view_name == "security":
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                response = render(
                    request,
                    "portal/staff/supervisor/partials/account/security.html",
                    {"password_form": PasswordChangeForm(request.user), "email": request.user.email},
                )
                response["HX-Trigger"] = json.dumps({"ui:toast": {"message": "Mot de passe mis à jour.", "tone": "success"}})
                return response
            return render(
                request,
                "portal/staff/supervisor/partials/account/security.html",
                {"password_form": password_form, "email": request.user.email},
                status=400,
            )
        if view_name == "preferences":
            form = UserPreferenceForm(request.POST, instance=preference)
            if form.is_valid():
                form.save()
                response = render(
                    request,
                    "portal/staff/supervisor/partials/account/preferences.html",
                    {"form": UserPreferenceForm(instance=preference)},
                )
                response["HX-Trigger"] = json.dumps({"ui:toast": {"message": "Préférences mises à jour.", "tone": "success"}})
                return response
            return render(
                request,
                "portal/staff/supervisor/partials/account/preferences.html",
                {"form": form},
                status=400,
            )

    if view_name == "profile":
        return render(
            request,
            "portal/staff/supervisor/partials/account/profile.html",
            _supervisor_account_context(request),
        )
    if view_name == "edit":
        return render(
            request,
            "portal/staff/supervisor/partials/account/edit.html",
            {"form": SystemProfileForm(instance=profile, user=request.user), "profile": profile},
        )
    if view_name == "security":
        return render(
            request,
            "portal/staff/supervisor/partials/account/security.html",
            {"password_form": PasswordChangeForm(request.user), "email": request.user.email},
        )
    return render(
        request,
        "portal/staff/supervisor/partials/account/preferences.html",
        {"form": UserPreferenceForm(instance=preference)},
    )


@_position_required({"academic_supervisor"})
def supervisor_student_attendance_print(request, student_id: int):
    branch = _resolve_supervisor_branch(request)
    if branch is None:
        return HttpResponseBadRequest("Aucune annexe rattachée.")
    class_id_raw = (request.GET.get("class_id") or "").strip()
    if not class_id_raw.isdigit():
        return HttpResponseBadRequest("Classe requise.")
    academic_class = get_object_or_404(AcademicClass, pk=int(class_id_raw), branch=branch, is_active=True)
    student = get_object_or_404(
        Student.objects.select_related("user", "inscription__candidature"),
        pk=student_id,
        inscription__candidature__branch=branch,
        user__academic_enrollments__academic_class=academic_class,
        user__academic_enrollments__branch=branch,
        user__academic_enrollments__is_active=True,
    )
    month_raw = (request.GET.get("month") or "").strip()
    try:
        month = datetime.strptime(month_raw, "%Y-%m").date().replace(day=1) if month_raw else timezone.localdate().replace(day=1)
    except ValueError:
        month = timezone.localdate().replace(day=1)
    report = build_attendance_monthly_report_context(branch=branch, academic_class=academic_class, month=month)
    row = next((item for item in report["attendance_report_rows"] if item["student"].pk == student.pk), None)
    return render(request, "portal/staff/supervisor/reports/individual_print.html", {
        "report_kind": "student",
        "branch": branch,
        "academic_class": academic_class,
        "student": student,
        "report_row": row,
        "period_start": report["attendance_report_month"],
        "period_end": report["attendance_report_month_end"],
        "generated_at": timezone.now(),
    })


@_position_required({"academic_supervisor"})
def supervisor_teacher_regularity_print(request, teacher_id: int):
    branch = _resolve_supervisor_branch(request)
    if branch is None:
        return HttpResponseBadRequest("Aucune annexe rattachée.")
    User = get_user_model()
    teacher = get_object_or_404(
        User.objects.select_related("profile"),
        pk=teacher_id,
        profile__branch=branch,
        profile__position="teacher",
    )
    week_raw = (request.GET.get("week_start") or "").strip()
    week_start = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
    try:
        if week_raw:
            week_start = datetime.strptime(week_raw, "%Y-%m-%d").date()
    except ValueError:
        pass
    report = build_teachers_weekly_report_context(branch=branch, week_start=week_start)
    row = next((item for item in report["report_teachers"] if item["id"] == teacher.pk), None)
    return render(request, "portal/staff/supervisor/reports/individual_print.html", {
        "report_kind": "teacher",
        "branch": branch,
        "teacher": teacher,
        "report_row": row,
        "period_start": report["report_week_start"],
        "period_end": report["report_week_end"],
        "generated_at": timezone.now(),
    })


@_position_required({"academic_supervisor"})
def supervisor_mark_student_attendance(request):
    if request.method != "POST":
        return _deny_portal_access(request)

    branch = _resolve_supervisor_branch(request)
    if branch is None:
        messages.error(request, "Aucune annexe n'est rattachee a ce compte.")
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
            .exclude(
                status__in={
                    AcademicScheduleEvent.STATUS_DRAFT,
                    AcademicScheduleEvent.STATUS_CANCELLED,
                }
            )
            .get()
        )
        roll_date = timezone.localtime(schedule_event.start_datetime).date()
        if roll_date > timezone.localdate():
            raise ValidationError("La présence étudiante ne peut être saisie avant le jour de la séance.")
        assert_roll_allows_editing(
            branch=branch,
            academic_class_id=schedule_event.academic_class_id,
            roll_date=roll_date,
            schedule_event_id=schedule_event.pk,
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
        if timezone.localtime(schedule_event.start_datetime).date() > timezone.localdate():
            raise ValidationError("Le constat enseignant ne peut être saisi avant le jour de la séance.")
        attendance_status = request.POST.get("status", "")
        result = mark_student_attendance(
            student=student,
            academic_class=schedule_event.academic_class,
            schedule_event=schedule_event,
            status=attendance_status,
            recorded_by=request.user,
            branch=branch,
            arrival_time=(
                _parse_optional_time(request.POST.get("arrival_time"))
                if attendance_status == StudentAttendance.STATUS_LATE
                else None
            ),
            justification=request.POST.get("justification", ""),
            is_justified=(
                attendance_status == StudentAttendance.STATUS_ABSENT
                and (request.POST.get("is_justified") or "").lower() in {"1", "true", "on", "yes"}
            ),
            observation=request.POST.get("observation", ""),
        )
        touch_roll_after_bulk_save(
            user=request.user,
            branch=branch,
            academic_class=schedule_event.academic_class,
            roll_date=roll_date,
            schedule_event=schedule_event,
        )
    except (AcademicScheduleEvent.DoesNotExist, Student.DoesNotExist):
        messages.error(request, "Selection invalide pour la saisie de presence etudiant.")
        return _redirect_supervisor_dashboard("attendance")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return _redirect_supervisor_dashboard("attendance")

    attendance = result["attendance"]
    messages.success(
        request,
        f"Presence etudiant enregistree: {attendance.student.full_name} - {attendance.get_status_display()}.",
    )
    return _redirect_supervisor_dashboard("attendance")


@_position_required({"academic_supervisor"})
def supervisor_mark_teacher_attendance(request):
    if request.method != "POST":
        return _deny_portal_access(request)

    branch = _resolve_supervisor_branch(request)
    if branch is None:
        messages.error(request, "Aucune annexe n'est rattachee a ce compte.")
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
            .exclude(
                status__in={
                    AcademicScheduleEvent.STATUS_DRAFT,
                    AcademicScheduleEvent.STATUS_CANCELLED,
                }
            )
            .get()
        )
        attendance_status = request.POST.get("status", "")
        result = mark_teacher_attendance(
            teacher=schedule_event.teacher,
            schedule_event=schedule_event,
            status=attendance_status,
            recorded_by=request.user,
            branch=branch,
            arrival_time=(
                _parse_optional_time(request.POST.get("arrival_time"))
                if attendance_status == TeacherAttendance.STATUS_LATE
                else None
            ),
            justification=request.POST.get("justification", ""),
            course_delivered=(
                False
                if attendance_status == TeacherAttendance.STATUS_ABSENT
                else True
                if request.POST.get("course_delivered") == "yes"
                else False
                if request.POST.get("course_delivered") == "no"
                else None
            ),
            observation=request.POST.get("observation", ""),
        )
    except AcademicScheduleEvent.DoesNotExist:
        if request.htmx:
            return HttpResponseBadRequest("Séance publiée introuvable dans votre annexe.")
        messages.error(request, "Cours introuvable pour la saisie de presence enseignant.")
        return _redirect_supervisor_dashboard("attendance")
    except ValidationError as exc:
        if request.htmx:
            return HttpResponseBadRequest(" ".join(exc.messages))
        messages.error(request, " ".join(exc.messages))
        return _redirect_supervisor_dashboard("attendance")

    attendance = result["attendance"]
    if request.htmx:
        response = render(
            request,
            "portal/staff/supervisor/partials/teacher_drawer.html",
            _build_teacher_drawer_context(
                branch=branch,
                teacher=schedule_event.teacher,
                event=schedule_event,
            ),
        )
        response["HX-Trigger"] = json.dumps(
            {
                "toast": (
                    f"Présence enregistrée : {attendance.get_status_display()}."
                ),
                "supervisor-attendance-updated": "",
            }
        )
        return response
    messages.success(
        request,
        f"Presence enseignant enregistree: {attendance.teacher.get_full_name() or attendance.teacher.username} - {attendance.get_status_display()}.",
    )
    return _redirect_supervisor_dashboard("attendance")


@_position_required({"academic_supervisor"})
@transaction.atomic
def supervisor_validate_lesson_log(request):
    """Approve or return a submitted lesson after the factual attendance check."""
    if request.method != "POST":
        return _deny_portal_access(request)

    branch = _resolve_supervisor_branch(request)
    if branch is None:
        return HttpResponseBadRequest("Aucune annexe n'est rattachée à ce compte.")

    event = None
    try:
        event = (
            AcademicScheduleEvent.objects.select_related("teacher", "academic_class", "ec", "branch")
            .filter(
                pk=request.POST.get("schedule_event_id"),
                branch=branch,
                event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
                is_active=True,
            )
            .exclude(status__in={AcademicScheduleEvent.STATUS_DRAFT, AcademicScheduleEvent.STATUS_CANCELLED})
            .get()
        )
        lesson_log = LessonLog.objects.select_related("teacher", "ec", "academic_class", "schedule_event").get(
            pk=request.POST.get("lesson_log_id"),
            branch=branch,
            schedule_event=event,
            teacher=event.teacher,
        )
        if timezone.localtime(event.start_datetime).date() > timezone.localdate():
            raise ValidationError("Un cahier ne peut pas être contrôlé avant le jour de la séance.")
        attendance = TeacherAttendance.objects.filter(
            branch=branch,
            teacher=event.teacher,
            schedule_event=event,
        ).first()
        if lesson_log.status != LessonLog.STATUS_SUBMITTED:
            raise ValidationError("Seul un cahier soumis peut être contrôlé.")
        decision = (request.POST.get("decision") or "approve").strip()
        review_comment = (request.POST.get("review_comment") or "").strip()
        review_fields = {
            "reviewed_by": request.user,
            "reviewed_at": timezone.now(),
            "review_comment": review_comment,
        }
        if decision == "return":
            if not review_comment:
                raise ValidationError("Indiquez le motif du retour à l'enseignant.")
            update_lesson_log(
                lesson_log,
                updated_by=request.user,
                status=LessonLog.STATUS_RETURNED,
                validated_by=None,
                **review_fields,
            )
            toast_message = "Cahier retourné à l'enseignant avec votre motif."
        elif decision == "approve":
            lesson_log_signature = get_signed_signature_for_subject(
                branch=branch,
                purpose=SignatureRequest.PURPOSE_LESSON_LOG,
                subject=lesson_log,
                signer=event.teacher,
                snapshot=build_lesson_log_signature_snapshot(lesson_log),
            )
            if lesson_log_signature is None:
                raise ValidationError(
                    "La signature de l'enseignant est absente ou ne correspond plus au cahier déclaré."
                )
            if (
                attendance is None
                or attendance.status not in {TeacherAttendance.STATUS_PRESENT, TeacherAttendance.STATUS_LATE}
                or attendance.course_delivered is not True
            ):
                raise ValidationError(
                    "Enregistrez d'abord une présence présente/en retard et confirmez que le cours a été assuré."
                )
            roll_sheet = AttendanceRollSheet.objects.filter(
                branch=branch,
                academic_class=event.academic_class,
                schedule_event=event,
                status=AttendanceRollSheet.STATUS_VALIDATED,
            ).first()
            if roll_sheet is None:
                raise ValidationError(
                    "Validez d'abord la feuille d'appel étudiant de cette séance avant d'approuver le cahier."
                )
            update_lesson_log(
                lesson_log,
                updated_by=request.user,
                status=LessonLog.STATUS_DONE,
                validated_by=request.user,
                **review_fields,
            )
            approve_signature(signature_request=lesson_log_signature, approver=request.user)
            toast_message = "Cahier approuvé : les heures éligibles ont été transmises aux honoraires."
        else:
            raise ValidationError("Décision de contrôle invalide.")
    except (AcademicScheduleEvent.DoesNotExist, LessonLog.DoesNotExist):
        return HttpResponseBadRequest("Séance ou cahier introuvable dans votre annexe.")
    except ValidationError as exc:
        if event is None:
            return HttpResponseBadRequest(" ".join(exc.messages))
        context = _build_teacher_drawer_context(
            branch=branch,
            teacher=event.teacher,
            event=event,
        )
        context["review_error"] = " ".join(exc.messages)
        response = render(request, "portal/staff/supervisor/partials/teacher_drawer.html", context)
        response.status_code = 400
        return response

    context = _build_teacher_drawer_context(branch=branch, teacher=event.teacher, event=event)
    response = render(request, "portal/staff/supervisor/partials/teacher_drawer.html", context)
    response["HX-Trigger"] = json.dumps(
        {
            "toast": toast_message,
            "supervisor-attendance-updated": "",
        }
    )
    return response


@_position_required({"academic_supervisor"})
def supervisor_save_lesson_log(request):
    return _removed_supervisor_capability()

    if request.method != "POST":
        return _deny_portal_access(request)

    branch = _resolve_supervisor_branch(request)
    if branch is None:
        messages.error(request, "Aucune annexe n'est rattachee a ce compte.")
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
        return _redirect_supervisor_dashboard("courses")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return _redirect_supervisor_dashboard("courses")

    messages.success(
        request,
        f"Cahier de texte enregistre pour {lesson_log.academic_class.display_name} - {lesson_log.ec.title}.",
    )
    return _redirect_supervisor_dashboard("courses")


@_position_required({"academic_supervisor"})
def supervisor_quick_search(request):
    branch = _resolve_supervisor_branch(request)
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
            Q(name__icontains=query)
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
            Q(academic_class__name__icontains=query)
            | Q(academic_class__programme__title__icontains=query)
            | Q(academic_class__level__icontains=query)
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
    branch = _resolve_supervisor_branch(request)
    query = (request.GET.get("q") or "").strip()
    if branch is None or len(query) < 2:
        return render(
            request,
            "portal/staff/supervisor/partials/student_options.html",
            {"items": []},
        )

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


@_position_required({"academic_supervisor"})
def supervisor_class_detail(request, class_id: int):
    branch = _resolve_supervisor_branch(request)
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

    context = build_class_detail_context(
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
def supervisor_planner_workspace(request):
    return _removed_supervisor_capability()

    branch, class_id, week_start = _parse_supervisor_planner_request(request)
    if branch is None:
        return render(
            request,
            "portal/staff/supervisor/partials/sg_planner_workspace.html",
            {"toast": {"level": "error", "message": "Aucune annexe n'est rattachee a ce compte."}},
        )
    if class_id is None:
        return render(
            request,
            "portal/staff/supervisor/partials/sg_planner_workspace.html",
            {"branch": branch, "academic_class": None},
        )

    context = build_class_detail_context(
        request,
        branch=branch,
        class_id=class_id,
        week_start=week_start,
    )
    context["planner_intent"] = (request.GET.get("intent") or "create").strip() or "create"
    _inject_planner_route_context(context, role_prefix="supervisor", workspace_target_id="#supervisor-workspace")
    return render(
        request,
        "portal/staff/supervisor/partials/sg_planner_workspace.html",
        context,
    )


@_position_required({"academic_supervisor"})
def supervisor_planner_hub(request):
    return _removed_supervisor_capability()

    branch, class_id, week_start = _parse_supervisor_planner_request(request)
    drawer_mode = (request.GET.get("drawer") or "").strip() == "1"

    def _maybe_open_drawer(response):
        if drawer_mode:
            response["HX-Trigger"] = "supervisor-drawer-open"
        return response

    if branch is None:
        return _maybe_open_drawer(render(
            request,
            "portal/staff/supervisor/partials/sg_planner_class_hub.html",
            {"toast": {"level": "error", "message": "Aucune annexe n'est rattachee a ce compte."}},
        ))
    if class_id is None:
        return _maybe_open_drawer(render(
            request,
            "portal/staff/supervisor/partials/sg_planner_class_hub.html",
            {"branch": branch, "academic_class": None},
        ))
    context = build_class_detail_context(
        request,
        branch=branch,
        class_id=class_id,
        week_start=week_start,
    )
    context["drawer"] = drawer_mode
    _inject_planner_route_context(context, role_prefix="supervisor", workspace_target_id="#supervisor-workspace")
    return _maybe_open_drawer(render(
        request,
        "portal/staff/supervisor/partials/sg_planner_class_hub.html",
        context,
    ))


@_position_required({"academic_supervisor"})
def supervisor_planner_view_workspace(request):
    return _removed_supervisor_capability()

    branch, class_id, week_start = _parse_supervisor_planner_request(request)
    if branch is None:
        return render(
            request,
            "portal/staff/supervisor/partials/sg_planner_view_workspace.html",
            {"toast": {"level": "error", "message": "Aucune annexe n'est rattachee a ce compte."}},
        )
    if class_id is None:
        return render(
            request,
            "portal/staff/supervisor/partials/sg_planner_view_workspace.html",
            {"branch": branch, "academic_class": None},
        )
    context = build_class_detail_context(
        request,
        branch=branch,
        class_id=class_id,
        week_start=week_start,
    )
    _inject_planner_route_context(context, role_prefix="supervisor", workspace_target_id="#supervisor-workspace")
    return render(
        request,
        "portal/staff/supervisor/partials/sg_planner_view_workspace.html",
        context,
    )


@_position_required({"academic_supervisor"})
def supervisor_weekly_slots_workspace(request, class_id: int, drawer_form=False):
    return _removed_supervisor_capability()

    branch = _resolve_supervisor_branch(request)
    if branch is None:
        return render(
            request,
            "portal/staff/supervisor/partials/sg_weekly_slots_workspace.html",
            {"toast": {"level": "error", "message": "Aucune annexe n'est rattachee a ce compte."}, "academic_class": None},
        )

    week_start_raw = (request.GET.get("week_start") or "").strip()
    week_start = timezone.localdate()
    if week_start_raw:
        try:
            week_start = datetime.strptime(week_start_raw, "%Y-%m-%d").date()
        except ValueError:
            week_start = timezone.localdate()

    edit_raw = (request.GET.get("edit") or request.GET.get("slot_id") or "").strip()
    editing_slot_id = int(edit_raw) if edit_raw.isdigit() else None

    drawer_form = bool(drawer_form) or (request.GET.get("drawer_form") or "").strip() == "1"

    def _maybe_open_drawer(response):
        if drawer_form:
            response["HX-Trigger"] = "supervisor-drawer-open"
        return response

    try:
        context = _build_weekly_slots_workspace_context(
            request,
            branch=branch,
            class_id=class_id,
            week_start=week_start,
            editing_slot_id=editing_slot_id,
        )
    except AcademicClass.DoesNotExist:
        template = "portal/staff/supervisor/partials/sg_weekly_slot_form_drawer.html" if drawer_form else "portal/staff/supervisor/partials/sg_weekly_slots_workspace.html"
        return _maybe_open_drawer(render(
            request,
            template,
            {
                "toast": {"level": "error", "message": "Classe introuvable pour cette annexe."},
                "academic_class": None,
            },
        ))

    _inject_planner_route_context(context, role_prefix="supervisor", workspace_target_id="#supervisor-workspace")
    template = "portal/staff/supervisor/partials/sg_weekly_slot_form_drawer.html" if drawer_form else "portal/staff/supervisor/partials/sg_weekly_slots_workspace.html"
    return _maybe_open_drawer(render(request, template, context))


@_position_required({"academic_supervisor"})
def supervisor_weekly_slot_save(request, class_id: int):
    return _removed_supervisor_capability()

    if request.method != "POST":
        return _deny_portal_access(request)

    branch = _resolve_supervisor_branch(request)
    if branch is None:
        return render(
            request,
            "portal/staff/supervisor/partials/sg_weekly_slots_workspace.html",
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

    User = get_user_model()

    try:
        academic_class = AcademicClass.objects.select_related("academic_year", "branch").get(
            pk=class_id,
            branch=branch,
            is_active=True,
        )

        if action == "delete":
            slot_raw = (request.POST.get("slot_id") or "").strip()
            if not slot_raw.isdigit():
                raise ValidationError("Creneau invalide.")
            slot = WeeklyScheduleSlot.objects.get(
                pk=int(slot_raw),
                academic_class=academic_class,
                branch=branch,
            )
            deactivate_weekly_schedule_slot(slot)
            toast = {"level": "success", "message": "Creneau retire de la grille hebdomadaire."}

        elif action in {"update", "create"}:
            ec = EC.objects.select_related("ue", "ue__semester").get(
                pk=request.POST.get("ec_id"),
                ue__semester__academic_class=academic_class,
            )
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
                slot = WeeklyScheduleSlot.objects.get(
                    pk=int(slot_raw),
                    academic_class=academic_class,
                    branch=branch,
                    is_active=True,
                )
                update_weekly_schedule_slot(
                    slot,
                    weekday=weekday,
                    ec=ec,
                    teacher=teacher,
                    start_time=start_t,
                    end_time=end_t,
                    room=room,
                    is_active=True,
                )
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

    except (
        AcademicClass.DoesNotExist,
        WeeklyScheduleSlot.DoesNotExist,
        EC.DoesNotExist,
        User.DoesNotExist,
    ):
        toast = {"level": "error", "message": "Donnee introuvable ou hors du perimetre de cette classe."}
    except ValidationError as exc:
        toast = {"level": "error", "message": " ".join(exc.messages)}

    try:
        context = _build_weekly_slots_workspace_context(
            request,
            branch=branch,
            class_id=class_id,
            week_start=week_start,
            editing_slot_id=None,
            toast=toast,
        )
    except AcademicClass.DoesNotExist:
        return render(
            request,
            "portal/staff/supervisor/partials/sg_weekly_slots_workspace.html",
            {
                "toast": {"level": "error", "message": "Classe introuvable pour cette annexe."},
                "academic_class": None,
            },
        )

    _inject_planner_route_context(context, role_prefix="supervisor", workspace_target_id="#supervisor-workspace")
    return render(request, "portal/staff/supervisor/partials/sg_weekly_slots_workspace.html", context)


@_position_required({"academic_supervisor"})
def supervisor_week_materialize(request, class_id: int):
    return _removed_supervisor_capability()

    if request.method != "POST":
        return _deny_portal_access(request)

    branch = _resolve_supervisor_branch(request)
    if branch is None:
        return render(
            request,
            "portal/staff/supervisor/partials/sg_weekly_slots_workspace.html",
            {"toast": {"level": "error", "message": "Aucune annexe n'est rattachee a ce compte."}, "academic_class": None},
        )

    week_start_raw = (request.POST.get("week_start") or "").strip()
    week_start = timezone.localdate()
    if week_start_raw:
        try:
            week_start = datetime.strptime(week_start_raw, "%Y-%m-%d").date()
        except ValueError:
            week_start = timezone.localdate()

    try:
        academic_class = AcademicClass.objects.select_related("academic_year", "branch").get(
            pk=class_id,
            branch=branch,
            is_active=True,
        )
        result = _materialize_period_from_weekly_slots(
            user=request.user,
            academic_class=academic_class,
            week_start=week_start,
            weeks_count=1,
        )
        toast = {
            "level": "success",
            "message": f"Semaine générée: {result['created']} cours créés ({result['skipped_existing']} déjà présents).",
        }
    except AcademicClass.DoesNotExist:
        toast = {"level": "error", "message": "Classe introuvable pour cette annexe."}

    context = _build_weekly_slots_workspace_context(
        request,
        branch=branch,
        class_id=class_id,
        week_start=week_start,
        editing_slot_id=None,
        toast=toast,
    )
    _inject_planner_route_context(context, role_prefix="supervisor", workspace_target_id="#supervisor-workspace")
    return render(request, "portal/staff/supervisor/partials/sg_weekly_slots_workspace.html", context)


@_position_required({"academic_supervisor"})
def supervisor_month_materialize(request, class_id: int):
    return _removed_supervisor_capability()

    if request.method != "POST":
        return _deny_portal_access(request)

    branch = _resolve_supervisor_branch(request)
    if branch is None:
        return render(
            request,
            "portal/staff/supervisor/partials/sg_weekly_slots_workspace.html",
            {"toast": {"level": "error", "message": "Aucune annexe n'est rattachee a ce compte."}, "academic_class": None},
        )

    week_start_raw = (request.POST.get("week_start") or "").strip()
    week_start = timezone.localdate()
    if week_start_raw:
        try:
            week_start = datetime.strptime(week_start_raw, "%Y-%m-%d").date()
        except ValueError:
            week_start = timezone.localdate()

    try:
        academic_class = AcademicClass.objects.select_related("academic_year", "branch").get(
            pk=class_id,
            branch=branch,
            is_active=True,
        )
        result = _materialize_period_from_weekly_slots(
            user=request.user,
            academic_class=academic_class,
            week_start=week_start,
            weeks_count=4,
        )
        toast = {
            "level": "success",
            "message": f"Mois pedagogique genere: {result['created']} cours crees ({result['skipped_existing']} deja presents).",
        }
    except AcademicClass.DoesNotExist:
        toast = {"level": "error", "message": "Classe introuvable pour cette annexe."}

    context = _build_weekly_slots_workspace_context(
        request,
        branch=branch,
        class_id=class_id,
        week_start=week_start,
        editing_slot_id=None,
        toast=toast,
    )
    _inject_planner_route_context(context, role_prefix="supervisor", workspace_target_id="#supervisor-workspace")
    return render(request, "portal/staff/supervisor/partials/sg_weekly_slots_workspace.html", context)


@_position_required({"academic_supervisor"})
def supervisor_create_schedule_event(request, class_id: int):
    return _removed_supervisor_capability()

    if request.method != "POST":
        return _deny_portal_access(request)

    branch = _resolve_supervisor_branch(request)
    if branch is None:
        return _deny_portal_access(request)

    User = get_user_model()
    academic_class = AcademicClass.objects.select_related("academic_year", "branch").get(
        pk=class_id,
        branch=branch,
        is_active=True,
    )
    ec = EC.objects.select_related("ue", "ue__semester").get(
        pk=request.POST.get("ec_id"),
        ue__semester__academic_class=academic_class,
    )
    teacher = User.objects.get(
        pk=request.POST.get("teacher_id"),
        is_active=True,
        profile__branch=branch,
        profile__position="teacher",
    )

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
    context = build_class_detail_context(
        request,
        branch=branch,
        class_id=class_id,
        week_start=week_start,
    )
    context["toast"] = toast
    context["planner_intent"] = (request.POST.get("planner_intent") or "create").strip() or "create"
    _inject_planner_route_context(context, role_prefix="supervisor", workspace_target_id="#supervisor-workspace")
    return render(request, "portal/staff/supervisor/partials/sg_planner_workspace.html", context)


def _hx_trigger_close_and_toast(response, *, message):
    response["HX-Trigger"] = json.dumps({"supervisor-drawer-close": "", "toast": message})
    return response


def _build_teacher_drawer_context(*, branch, teacher, event):
    attendance = TeacherAttendance.objects.filter(
        branch=branch,
        teacher=teacher,
        schedule_event=event,
    ).first()
    lesson_log = (
        LessonLog.objects.select_related("validated_by")
        .filter(branch=branch, teacher=teacher, schedule_event=event)
        .order_by("-updated_at", "-id")
        .first()
    )
    roll_sheet = AttendanceRollSheet.objects.filter(
        branch=branch,
        academic_class=event.academic_class,
        schedule_event=event,
    ).first()
    student_attendance_qs = StudentAttendance.objects.filter(
        branch=branch,
        academic_class=event.academic_class,
        schedule_event=event,
    )
    student_attendance_counts = {
        "present": student_attendance_qs.filter(status=StudentAttendance.STATUS_PRESENT).count(),
        "late": student_attendance_qs.filter(status=StudentAttendance.STATUS_LATE).count(),
        "absent": student_attendance_qs.filter(status=StudentAttendance.STATUS_ABSENT).count(),
    }
    lesson_log_signature = None
    if lesson_log is not None:
        lesson_log_signature = get_signed_signature_for_subject(
            branch=branch,
            purpose=SignatureRequest.PURPOSE_LESSON_LOG,
            subject=lesson_log,
            signer=teacher,
            snapshot=build_lesson_log_signature_snapshot(lesson_log),
        )
    return {
        "teacher": teacher,
        "selected_event": event,
        "teacher_attendance": attendance,
        "lesson_log": lesson_log,
        "lesson_log_signature": lesson_log_signature,
        "lesson_log_signature_ready": lesson_log_signature is not None,
        "attendance_roll_sheet": roll_sheet,
        "student_attendance_total": student_attendance_qs.count(),
        "student_attendance_counts": student_attendance_counts,
        "student_attendance_ready": bool(
            roll_sheet and roll_sheet.status == AttendanceRollSheet.STATUS_VALIDATED
        ),
    }


@_position_required({"academic_supervisor"})
def supervisor_teacher_drawer(request):
    branch = _resolve_supervisor_branch(request)
    teacher_id_raw = (request.GET.get("teacher_id") or "").strip()
    event_id_raw = (request.GET.get("schedule_event_id") or "").strip()
    if branch is None or not teacher_id_raw.isdigit() or not event_id_raw.isdigit():
        return render(request, "portal/staff/supervisor/partials/teacher_drawer.html", {"teacher": None})

    event = (
        AcademicScheduleEvent.objects.select_related("teacher", "academic_class", "ec", "branch")
        .filter(
            pk=int(event_id_raw),
            branch=branch,
            teacher_id=int(teacher_id_raw),
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            is_active=True,
        )
        .exclude(
            status__in={
                AcademicScheduleEvent.STATUS_DRAFT,
                AcademicScheduleEvent.STATUS_CANCELLED,
            }
        )
        .first()
    )
    if event is None or event.teacher is None:
        return render(request, "portal/staff/supervisor/partials/teacher_drawer.html", {"teacher": None})

    response = render(
        request,
        "portal/staff/supervisor/partials/teacher_drawer.html",
        _build_teacher_drawer_context(branch=branch, teacher=event.teacher, event=event),
    )
    response["HX-Trigger"] = "supervisor-drawer-open"
    return response


@_position_required({"academic_supervisor"})
def supervisor_toggle_teacher_presence(request):
    return _removed_supervisor_capability()


@_position_required({"academic_supervisor"})
def supervisor_assign_replacement(request):
    return _removed_supervisor_capability()

    if request.method != "POST":
        return _deny_portal_access(request)
    branch = _resolve_supervisor_branch(request)
    User = get_user_model()
    try:
        event = AcademicScheduleEvent.objects.select_related("teacher", "branch").get(
            pk=request.POST.get("schedule_event_id"), branch=branch
        )
        replacement = User.objects.get(
            pk=request.POST.get("replacement_teacher_id"),
            profile__branch=branch,
            profile__position="teacher",
        )
        assign_session_replacement(
            event=event,
            replacement_teacher=replacement,
            supervisor=request.user,
            note=(request.POST.get("note") or "").strip(),
        )
        message = f"{replacement.get_full_name() or replacement.username} affecte en remplacement."
    except (AcademicScheduleEvent.DoesNotExist, User.DoesNotExist):
        message = "Selection invalide pour le remplacement."

    return _hx_trigger_close_and_toast(
        render(
            request,
            "portal/staff/supervisor/partials/panel_teachers.html",
            build_teachers_section_context(branch=branch),
        ),
        message=message,
    )


@_position_required({"academic_supervisor"})
def supervisor_signal_teacher_incident(request):
    return _removed_supervisor_capability()


@_position_required({"academic_supervisor"})
def supervisor_convocation_drawer(request):
    return _removed_supervisor_capability()

    branch = _resolve_supervisor_branch(request)
    target_type = (request.GET.get("target_type") or Convocation.TARGET_STUDENT).strip()
    target_id_raw = (request.GET.get("target_id") or "").strip()
    case_id = (request.GET.get("case_id") or "").strip()
    context = {
        "target_type": target_type,
        "target_id": target_id_raw,
        "case_id": case_id,
        "motif_choices": (
            ["Absences répétées", "Retards récurrents", "Comportement", "Tenue / stage non conforme", "Autre"]
            if target_type == Convocation.TARGET_STUDENT
            else ["Retards à la prise de service", "Absences", "Manquement pédagogique", "Entretien", "Autre"]
        ),
        "channel_choices": Convocation.CHANNEL_CHOICES,
        "dest_choices": Convocation.DEST_CHOICES,
    }
    if branch and target_type == Convocation.TARGET_STUDENT and target_id_raw.isdigit():
        context["student"] = (
            Student.objects.select_related("user", "inscription__candidature")
            .filter(pk=int(target_id_raw), inscription__candidature__branch=branch)
            .first()
        )
    elif branch and target_type == Convocation.TARGET_TEACHER and target_id_raw.isdigit():
        User = get_user_model()
        context["teacher"] = User.objects.filter(
            pk=int(target_id_raw), profile__branch=branch, profile__position="teacher"
        ).first()

    response = render(request, "portal/staff/supervisor/partials/convocation_drawer.html", context)
    response["HX-Trigger"] = "supervisor-drawer-open"
    return response


@_position_required({"academic_supervisor"})
def supervisor_convocation_create(request):
    return _removed_supervisor_capability()

    if request.method != "POST":
        return _deny_portal_access(request)
    branch = _resolve_supervisor_branch(request)
    if branch is None:
        return _hx_trigger_close_and_toast(
            HttpResponse(""), message="Aucune annexe n'est rattachee a ce compte."
        )

    target_type = request.POST.get("target_type") or Convocation.TARGET_STUDENT
    target_id_raw = (request.POST.get("target_id") or "").strip()
    case_id_raw = (request.POST.get("case_id") or "").strip()
    User = get_user_model()
    try:
        student = teacher = None
        student_case = teacher_case = None
        if target_type == Convocation.TARGET_STUDENT:
            student = Student.objects.select_related("inscription__candidature").get(
                pk=target_id_raw, inscription__candidature__branch=branch
            )
            if case_id_raw.isdigit():
                student_case = StudentCase.objects.filter(pk=int(case_id_raw), branch=branch).first()
        else:
            teacher = User.objects.get(pk=target_id_raw, profile__branch=branch, profile__position="teacher")
            if case_id_raw.isdigit():
                teacher_case = TeacherCase.objects.filter(pk=int(case_id_raw), branch=branch).first()

        create_convocation(
            target_type=target_type,
            branch=branch,
            student=student,
            teacher=teacher,
            student_case=student_case,
            teacher_case=teacher_case,
            motif=(request.POST.get("motif") or "").strip(),
            channel=(request.POST.get("channel") or "").strip(),
            scheduled_date=request.POST.get("scheduled_date"),
            scheduled_time=request.POST.get("scheduled_time"),
            message=(request.POST.get("message") or "").strip(),
            destinataire=(request.POST.get("destinataire") or "").strip(),
            created_by=request.user,
        )
        toast_message = "Convocation enregistree."
    except (Student.DoesNotExist, User.DoesNotExist):
        toast_message = "Destinataire introuvable pour cette annexe."
    except ValidationError as exc:
        toast_message = " ".join(getattr(exc, "messages", [str(exc)]))

    return _hx_trigger_close_and_toast(HttpResponse(""), message=toast_message)
