"""Espaces de compte institutionnel, affiches exclusivement dans Portal."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch

from accounts.access import get_user_position
from accounts.forms import SystemProfileForm
from accounts.models import Profile
from portal.permissions import get_post_login_portal_url


def _require_system_account(request):
    if get_user_position(request.user):
        return None
    messages.info(request, "Cet espace est reserve aux comptes institutionnels.")
    return redirect("accounts:profile")


def _dashboard_url(request):
    try:
        return get_post_login_portal_url(request.user)
    except NoReverseMatch:
        # The isolated test URL configuration deliberately excludes some
        # optional dashboards (for example Marketing).  Keep a safe internal
        # fallback rather than sending a SYSTEM account to a public profile.
        return reverse("accounts:dashboard_redirect")


@login_required
def system_profile(request):
    denied = _require_system_account(request)
    if denied:
        return denied
    return redirect("accounts_portal:system_profile_edit")


@login_required
def system_profile_edit(request):
    denied = _require_system_account(request)
    if denied:
        return denied

    profile, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = SystemProfileForm(request.POST, request.FILES, instance=profile, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Vos informations de compte ont ete mises a jour.")
            return redirect(_dashboard_url(request))
    else:
        form = SystemProfileForm(instance=profile, user=request.user)

    return render(request, "portal/system_profile_edit.html", {
        "form": form,
        "profile": profile,
        "profile_position": get_user_position(request.user),
        "dashboard_url": _dashboard_url(request),
    })


@login_required
def system_security(request):
    denied = _require_system_account(request)
    if denied:
        return denied
    return render(request, "portal/system_security.html", {
        "dashboard_url": _dashboard_url(request),
        "password_change_url": reverse("accounts_portal:system_change_password"),
        "profile_edit_url": reverse("accounts_portal:system_profile_edit"),
        "email": request.user.email,
    })
