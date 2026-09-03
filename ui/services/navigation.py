"""Build presentation-only navigation from the official access policy."""

from __future__ import annotations

from urllib.parse import urlencode

from django.urls import NoReverseMatch, reverse

from accounts.access import can_access, get_user_position, get_user_scope


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


def build_supervisor_navigation(
    user,
    *,
    active_section="home",
    badges=None,
    selected_class_id=None,
):
    """Build the UI Core navigation for an authorized academic supervisor."""

    if get_user_position(user) != "academic_supervisor":
        return []

    badges = badges or {}
    groups = (
        (
            "Pilotage",
            (
                ("home", "Vue générale", "layout-dashboard"),
                ("classes", "Classes", "school"),
            ),
        ),
        (
            "Supervision opérationnelle",
            (
                ("attendance", "Présence étudiants", "list-checks"),
                ("teachers", "Séances à superviser", "clipboard-check"),
            ),
        ),
        (
            "Organisation",
            (
                ("schedule", "Emploi du temps", "calendar-range"),
            ),
        ),
        (
            "Transmission",
            (
                ("signals", "Signalements", "send"),
                ("reports", "Rapports", "file-text"),
            ),
        ),
    )
    dashboard_url = _url("accounts_portal:portal_dashboard")
    workflow_url = _url("accounts_portal:supervisor_workflow_workspace")
    staff_messaging_url = _url("accounts_portal:staff_messaging")
    staff_salary_url = _url("accounts_portal:staff_salary")
    navigation = []

    for label, sections in groups:
        items = []
        for key, item_label, icon in sections:
            params = {"section": key}
            if selected_class_id and key not in {"signals"}:
                params["class_id"] = selected_class_id
            query = urlencode(params)
            items.append(
                {
                    "label": item_label,
                    "url": f"{dashboard_url}?{query}",
                    "icon": icon,
                    "active": key == active_section,
                    "badge": badges.get(key),
                    "disabled": dashboard_url == "#" or workflow_url == "#",
                    "hx_get": f"{workflow_url}?{query}",
                    "hx_target": "#supervisor-workspace",
                    "hx_swap": "innerHTML",
                    "hx_push_url": f"{dashboard_url}?{query}",
                    "nav_key": key,
                }
            )
        navigation.append({"label": label, "items": items})

    # Espace personnel : messagerie interne et salaire via les endpoints
    # génériques staff, échangés dans le workspace superviseur.
    if staff_messaging_url != "#":
        personal_items = [
            {
                "label": "Messagerie",
                "url": dashboard_url,
                "icon": "mail",
                "active": active_section == "messagerie",
                "badge": badges.get("messagerie"),
                "hx_get": f"{staff_messaging_url}?dash=supervisor",
                "hx_target": "#supervisor-workspace",
                "hx_swap": "innerHTML",
                "hx_push_url": dashboard_url,
                "nav_key": "messagerie",
            },
        ]
        if staff_salary_url != "#":
            personal_items.append(
                {
                    "label": "Mon salaire",
                    "url": dashboard_url,
                    "icon": "wallet",
                    "active": active_section == "salaire",
                    "hx_get": f"{staff_salary_url}?dash=supervisor",
                    "hx_target": "#supervisor-workspace",
                    "hx_swap": "innerHTML",
                    "hx_push_url": dashboard_url,
                    "nav_key": "salaire",
                }
            )
        navigation.append({"label": "Espace personnel", "items": personal_items})
    return navigation


def build_director_navigation(user, *, active_section="home", badges=None):
    """Build navigation for an already authorized academic director."""

    badges = badges or {}
    scope = get_user_scope(user)
    authorized = can_access(user, "view_dashboard", "director_studies") or bool(
        scope.get("is_global")
    )
    if not authorized:
        return []

    section_groups = (
        (
            "Pilotage",
            (
                ("home", "Vue générale", "layout-dashboard"),
                ("calendrier", "Calendrier académique", "calendar-days"),
            ),
        ),
        (
            "Organisation académique",
            (
                ("programme", "Classes et maquettes", "book-open"),
                ("planification", "Emplois du temps", "calendar-range"),
                ("enseignants", "Enseignants", "users"),
            ),
        ),
        (
            "Évaluations",
            (
                ("evaluations_calendar", "Sessions et examens", "clipboard-check"),
                ("evaluations", "Notes et résultats", "bar-chart-3"),
            ),
        ),
        (
            "Suivi académique",
            (
                ("correspondances", "Documents académiques", "files"),
                ("transferts", "Transferts", "arrow-left-right"),
            ),
        ),
        (
            "Espace personnel",
            (
                ("messagerie", "Messagerie interne", "messages-square"),
                ("salaire", "Mon salaire", "badge-dollar-sign"),
                ("settings", "Paramètres de l'annexe", "settings-2"),
            ),
        ),
    )
    dashboard_url = _url("accounts_portal:portal_dashboard")
    workspace_url = _url("accounts_portal:director_workspace")
    navigation = []
    for group_label, sections in section_groups:
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
        navigation.append({"label": group_label, "items": items})
    return navigation
