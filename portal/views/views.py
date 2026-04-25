from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse

from accounts.access import can_access, get_user_scope
from portal.permissions import get_user_role as get_portal_user_role, portal_redirect
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


@login_required
def portal_home(request):
    return portal_redirect(request)


@login_required
def portal_dashboard(request):
    portal_role = get_portal_user_role(request.user)

    if portal_role == "student" and can_access(request.user, "view_portal", "student"):
        return redirect("accounts_portal:portal_student")

    if get_user_scope(request.user).get("role") == "teacher" and can_access(request.user, "view_portal", "teacher"):
        return redirect("accounts_portal:portal_teacher")

    if portal_role == "staff" and can_access(request.user, "view_portal", "staff"):
        return redirect("accounts_portal:portal_staff")

    if portal_role == "admin":
        return redirect("admin:index")

    context = _build_portal_context(
        request,
        page_title="Portail - Acces limite",
        module_cards=["Modules bientot disponibles"],
    )
    return render(request, "portal/dashboard.html", context)


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
