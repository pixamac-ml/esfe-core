from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse

from accounts.access import can_access, get_user_scope


def _build_portal_context(request, *, page_title, module_cards):
    scope = get_user_scope(request.user)
    user_display_name = request.user.get_full_name() or request.user.username

    return {
        "page_title": page_title,
        "user_display_name": user_display_name,
        "detected_role": scope.get("role") or "public",
        "scope": scope,
        "module_cards": module_cards,
        "welcome_message": f"Bienvenue {user_display_name}, vous êtes connecté en tant que {scope.get('role') or 'public'}",
    }


def _deny_portal_access(request):
    return HttpResponseForbidden("Accès portail refusé.")


@login_required
def portal_home(request):
    return redirect("accounts_portal:portal_dashboard")


@login_required
def portal_dashboard(request):
    scope = get_user_scope(request.user)
    role = scope.get("role")

    if role == "student" and can_access(request.user, "view_portal", "student"):
        return redirect("accounts_portal:portal_student")

    if role == "teacher" and can_access(request.user, "view_portal", "teacher"):
        return redirect("accounts_portal:portal_teacher")

    if role in {"staff_admin", "directeur_etudes"} and can_access(request.user, "view_portal", "staff"):
        return redirect("accounts_portal:portal_staff")

    if role == "super_admin" and can_access(request.user, "view_portal", "dashboard"):
        context = _build_portal_context(
            request,
            page_title="Portail - Dashboard global",
            module_cards=[
                "Gestion étudiants",
                "Documents",
                "Cours",
                "Finance",
            ],
        )
        return render(request, "portal/dashboard.html", context)

    # Fallback parallèle sans toucher le flux legacy.
    context = _build_portal_context(
        request,
        page_title="Portail - Accès limité",
        module_cards=["Modules bientôt disponibles"],
    )
    return render(request, "portal/dashboard.html", context)


@login_required
def student_portal(request):
    if not can_access(request.user, "view_portal", "student"):
        return _deny_portal_access(request)

    context = _build_portal_context(
        request,
        page_title="Portail étudiant",
        module_cards=[
            "Mes cours",
            "Mes documents",
            "Mes paiements",
            "Mon profil",
        ],
    )
    return render(request, "portal/student.html", context)


@login_required
def staff_portal(request):
    if not can_access(request.user, "view_portal", "staff"):
        return _deny_portal_access(request)

    context = _build_portal_context(
        request,
        page_title="Portail staff",
        module_cards=[
            "Gestion étudiants",
            "Documents",
            "Admissions",
            "Finance",
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
            "Évaluations",
            "Documents",
            "Classes",
        ],
    )
    return render(request, "portal/teacher.html", context)


def get_post_login_portal_url(user):
    """Routeur post-login basé sur le scope centralisé."""

    scope = get_user_scope(user)
    role = scope.get("role")

    if role == "student" and can_access(user, "view_portal", "student"):
        return reverse("accounts_portal:portal_student")

    if role == "teacher" and can_access(user, "view_portal", "teacher"):
        return reverse("accounts_portal:portal_teacher")

    if role in {"staff_admin", "directeur_etudes"} and can_access(user, "view_portal", "staff"):
        return reverse("accounts_portal:portal_staff")

    if role == "super_admin" and can_access(user, "view_portal", "dashboard"):
        return reverse("accounts_portal:portal_dashboard")

    return reverse("accounts_portal:portal_dashboard")

