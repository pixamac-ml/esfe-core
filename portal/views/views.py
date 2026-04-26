from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse

from accounts.access import can_access, get_user_position, get_user_scope
from portal.permissions import get_post_login_portal_url, get_user_role as get_portal_user_role
from secretary.permissions import is_secretary


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
    return redirect("accounts:executive_dashboard")


@_position_required({"academic_supervisor"})
def supervisor_portal(request):
    context = _build_portal_context(
        request,
        page_title="Dashboard supervision academique",
        module_cards=[
            "Suivi des classes",
            "Suivi des absences",
            "Suivi pedagogique",
        ],
    )
    return render(request, "portal/staff/supervisor_dashboard.html", context)
