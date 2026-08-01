"""Build presentation-only navigation from the official access policy."""

from __future__ import annotations

from urllib.parse import urlencode

from django.urls import NoReverseMatch, reverse

from accounts.access import can_access, get_user_scope


def _url(name, fallback="#"):
    try:
        return reverse(name)
    except NoReverseMatch:
        return fallback


def _item(label, name, icon, path, badge=None):
    url = _url(name)
    return {
        "label": label,
        "url": url,
        "icon": icon,
        "active": bool(url != "#" and (path == url or path.startswith(f"{url.rstrip('/')}/"))),
        "badge": badge,
        "disabled": url == "#",
    }


def build_navigation(user, *, current_path="", badges=None):
    """Return navigation using, never replacing, the official access policy."""

    badges = badges or {}
    scope = get_user_scope(user)
    has_scope = bool(scope.get("is_global") or scope.get("branch"))
    groups = [
        {
            "label": "Espace personnel",
            "items": [
                _item("Accueil du portail", "accounts_portal:portal_home", "house", current_path),
                _item("Mon compte", "accounts_portal:system_profile", "user-round", current_path),
            ],
        }
    ]

    workspace_items = []
    candidates = (
        ("view_portal", "student", "Études", "accounts_portal:portal_student", "graduation-cap"),
        ("view_portal", "teacher", "Enseignement", "accounts_portal:portal_teacher", "presentation"),
        ("view_dashboard", "manager", "Gestion d'annexe", "accounts_portal:portal_annex_manager", "building-2"),
        ("view_dashboard", "admissions", "Admissions", "accounts_portal:portal_admissions", "user-plus"),
        ("view_dashboard", "finance", "Finance", "accounts_portal:portal_finance", "wallet-cards"),
        ("view_dashboard", "director_studies", "Direction des études", "accounts_portal:portal_director", "library"),
        ("view_dashboard", "executive", "Direction générale", "accounts_portal:portal_dg", "landmark"),
    )
    for action, resource, label, url_name, icon in candidates:
        if has_scope and can_access(user, action, resource):
            workspace_items.append(
                _item(label, url_name, icon, current_path, badges.get(resource))
            )

    if has_scope and can_access(user, "view_portal", "dashboard"):
        workspace_items.append(
            _item("Administration IT", "accounts_portal:portal_it", "shield-check", current_path)
        )

    if workspace_items:
        groups.append({"label": "Espaces autorisés", "items": workspace_items})
    return groups


def build_director_navigation(user, *, active_section="home", badges=None):
    """Build navigation for an already authorized academic director."""

    badges = badges or {}
    scope = get_user_scope(user)
    authorized = can_access(user, "view_dashboard", "director_studies") or bool(
        scope.get("is_global")
    )
    if not authorized:
        return []

    sections = (
        ("home", "Vue générale", "layout-dashboard"),
        ("calendrier", "Calendrier", "calendar-days"),
        ("evaluations_calendar", "Sessions d'évaluations", "clipboard-check"),
        ("evaluations", "Résultats et notes", "bar-chart-3"),
        ("enseignants", "Enseignants", "users"),
        ("programme", "Programmes et classes", "book-open"),
        ("planification", "Emploi du temps", "calendar-range"),
        ("correspondances", "Documents", "mail"),
    )
    dashboard_url = _url("accounts_portal:portal_dashboard")
    workspace_url = _url("accounts_portal:director_workspace")
    items = []
    for key, label, icon in sections:
        query = urlencode({"section": key})
        items.append(
            {
                "label": label,
                "url": f"{dashboard_url}?{query}",
                "icon": icon,
                "active": key == active_section,
                "badge": badges.get(key),
                "disabled": dashboard_url == "#" or workspace_url == "#",
                "hx_get": f"{workspace_url}?{query}",
                "hx_target": "#director-workspace",
                "hx_swap": "innerHTML",
                "hx_push_url": f"{dashboard_url}?{query}",
                "nav_key": key,
            }
        )
    return [{"label": "Pilotage académique", "items": items}]
