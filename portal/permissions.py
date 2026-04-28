from __future__ import annotations

from functools import wraps

from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse

from accounts.access import (
    get_user_groups,
    get_user_position,
    get_user_profile_role,
    get_user_role as get_canonical_user_role,
)
def get_user_role(user):
    if not getattr(user, "is_authenticated", False):
        return None

    canonical_role = get_canonical_user_role(user)
    if canonical_role == "student":
        return "student"
    if canonical_role in {"staff_admin", "directeur_etudes", "teacher"}:
        return "staff"
    if canonical_role == "super_admin":
        return "admin"

    profile_role = get_user_profile_role(user)
    if profile_role == "student":
        return "student"
    if profile_role in {"teacher", "admissions", "finance", "executive", "secretary", "superadmin"}:
        return "staff" if profile_role != "superadmin" else "admin"

    groups = set(get_user_groups(user))
    if groups.intersection({"students", "student"}):
        return "student"
    if groups.intersection(
        {
            "staff",
            "teacher",
            "teachers",
            "admissions",
            "admissions_managers",
            "finance",
            "finance_agents",
            "gestionnaire",
            "manager",
            "executive",
            "executive_director",
            "secretary",
            "secretaries",
        }
    ):
        return "staff"

    if getattr(user, "is_superuser", False):
        return "admin"

    return None


def role_required(expected_role):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            role = get_user_role(request.user)
            if role != expected_role:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def get_post_login_portal_url(user):
    if not getattr(user, "is_authenticated", False):
        return reverse("accounts_portal:portal_home")

    position = get_user_position(user)
    if position in {"finance_manager", "payment_agent"}:
        return reverse("accounts_portal:portal_finance")
    if position == "secretary":
        return reverse("accounts_portal:portal_secretary")
    if position == "admissions":
        return reverse("accounts_portal:portal_admissions")
    if position in {"director_of_studies", "executive_director", "super_admin"}:
        return reverse("accounts_portal:portal_director")
    if position == "academic_supervisor":
        return reverse("accounts_portal:portal_supervisor")
    if position == "it_support":
        return reverse("accounts_portal:portal_it")

    role = get_user_role(user)
    if role == "student":
        return reverse("portal_student:dashboard")
    if role == "staff" and get_user_profile_role(user) == "finance":
        return reverse("accounts:finance_dashboard")
    if role == "staff" and get_user_profile_role(user) == "admissions":
        return reverse("accounts:admissions_dashboard")
    if role == "staff":
        return reverse("accounts_portal:portal_staff")
    if role == "admin":
        return reverse("admin:index")

    return reverse("accounts_portal:portal_home")


def portal_redirect(request):
    return redirect(get_post_login_portal_url(request.user))
