"""Compatibility entrypoint for Admissions inside the manager workspace."""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


@login_required
def admissions_dashboard(request):
    """Open Admissions in the certified DE shell, never in a parallel dashboard."""

    if (
        settings.AUTH_PORTAL_ROUTING_V2_ENABLED
        and request.resolver_match
        and request.resolver_match.namespace == "accounts"
    ):
        return redirect("accounts_portal:portal_admissions")

    from accounts.dashboards.manager_dashboard import manager_dashboard

    return manager_dashboard(request, default_section="candidatures")
