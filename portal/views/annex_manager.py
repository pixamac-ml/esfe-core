"""Entrée Portal officielle de la gestionnaire d'annexe."""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from accounts.dashboards.manager_dashboard import (
    manager_dashboard,
    manager_subcontent,
    manager_workspace,
)


def annex_manager_portal(request):
    return manager_dashboard(request)


def annex_manager_workspace(request):
    """Return only the Gestionnaire workspace for certified HTMX navigation."""

    return manager_workspace(request)


def annex_manager_subcontent(request):
    """Return only the active Gestionnaire subview for tab navigation."""

    return manager_subcontent(request)


@login_required
def legacy_manager_redirect(request):
    return redirect("accounts_portal:portal_annex_manager")


def legacy_manager_entry(request):
    if settings.AUTH_PORTAL_ROUTING_V2_ENABLED:
        return legacy_manager_redirect(request)
    return manager_dashboard(request)


@login_required
def access_regularization(request):
    """État contrôlé : aucun dashboard approximatif n'est autorisé."""
    return render(request, "portal/access_regularization.html", status=403)
