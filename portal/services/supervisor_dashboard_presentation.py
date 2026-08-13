"""Presentation contracts for the Supervisor UI Core dashboard."""

from urllib.parse import urlencode

from django.urls import reverse

from notification_center.selectors import get_user_unread_count
from ui.services.navigation import build_supervisor_navigation


def _dashboard_url(section, selected_class_id=None, active_view=None):
    params = {"section": section}
    if active_view:
        params["view"] = active_view
    if selected_class_id and section != "signals":
        params["class_id"] = selected_class_id
    return f"{reverse('accounts_portal:portal_dashboard')}?{urlencode(params)}"


def _workspace_url(section, selected_class_id=None, active_view=None):
    params = {"section": section}
    if active_view:
        params["view"] = active_view
    if selected_class_id:
        params["class_id"] = selected_class_id
    return f"{reverse('accounts_portal:supervisor_workflow_workspace')}?{urlencode(params)}"


_SECTION_VIEWS = {
    "home": (
        ("overview", "Vue d'ensemble", "layout-dashboard"),
    ),
    "classes": (
        ("overview", "Vue d'ensemble", "layout-grid"),
        ("students", "Étudiants", "users"),
    ),
    "attendance": (
        ("overview", "Vue d'ensemble", "bar-chart-3"),
        ("call", "Appel du jour", "list-checks"),
        ("history", "Historique", "history"),
        ("alerts", "Alertes", "triangle-alert"),
    ),
    "teachers": (
        ("overview", "Vue d'ensemble", "bar-chart-3"),
        ("today", "Présence du jour", "user-check"),
        ("history", "Historique", "history"),
    ),
    "schedule": (
        ("today", "Aujourd'hui", "calendar-check"),
        ("week", "Semaine publiée", "calendar-range"),
    ),
    "signals": (
        ("overview", "Vue d'ensemble", "layout-dashboard"),
        ("new", "Nouveau signalement", "send"),
        ("transmitted", "Déjà transmis", "check-check"),
    ),
    "reports": (
        ("overview", "Vue d'ensemble", "files"),
        ("students", "Assiduité étudiants", "users"),
        ("teachers", "Régularité enseignants", "presentation"),
        ("transmitted", "Signalements transmis", "send"),
    ),
}


def _tabs(section, active_view, selected_class_id=None):
    dashboard_url = reverse("accounts_portal:portal_dashboard")
    workspace_url = reverse("accounts_portal:supervisor_workflow_workspace")
    items = []
    for view, label, icon in _SECTION_VIEWS.get(section, ()):
        params = {"section": section, "view": view}
        if selected_class_id and section != "signals":
            params["class_id"] = selected_class_id
        canonical_query = urlencode(params)
        fragment_query = urlencode({**params, "fragment": "subcontent"})
        items.append(
            {
                "id": view,
                "label": label,
                "icon": icon,
                "href": f"{dashboard_url}?{canonical_query}",
                "hx_get": f"{workspace_url}?{fragment_query}",
                "hx_target": "#supervisor-section-content",
                "hx_swap": "innerHTML",
                "hx_push_url": f"{dashboard_url}?{canonical_query}",
                "hx_indicator": "#supervisor-section-loading",
                "hx_sync": "#supervisor-section-content:replace",
            }
        )
    return items


def build_supervisor_dashboard_presentation(request, workspace):
    """Map branch-scoped supervisor data to presentation-only UI Core contracts."""

    active_section = workspace.get("section") or "home"
    active_view = workspace.get("active_view") or "overview"
    branch = workspace.get("branch")
    selected_class_id = workspace.get("selected_class_id")
    open_cases_count = workspace.get("open_cases_count") or 0
    unread_count = get_user_unread_count(request.user)

    return {
        "supervisor_navigation": build_supervisor_navigation(
            request.user,
            active_section=active_section,
            badges={"signals": open_cases_count or None},
            selected_class_id=selected_class_id,
        ),
        "supervisor_active_section": active_section,
        "supervisor_active_view": active_view,
        "supervisor_tabs": _tabs(active_section, active_view, selected_class_id),
        "supervisor_context_label": getattr(branch, "name", "") or "Annexe requise",
        "supervisor_dashboard_url": _dashboard_url(active_section, selected_class_id, active_view),
        "supervisor_workspace_url": _workspace_url(active_section, selected_class_id, active_view),
        "supervisor_class_picker_url": _workspace_url(active_section, active_view=active_view),
        "notification_count": unread_count,
        "notifications_url": reverse("notification_center:notifications"),
    }
