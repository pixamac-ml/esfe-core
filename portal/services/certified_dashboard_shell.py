"""Contract for the single certified management dashboard shell.

The Director of Studies dashboard is the canonical shell for every management
role. Business services remain role-specific; this module only normalizes the
presentation contract consumed by ``portal/staff/director_dashboard.html``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from urllib.parse import urlencode

from django.db import OperationalError, ProgrammingError
from django.urls import reverse

from accounts.access import get_user_scope
from notification_center.selectors import get_user_unread_count


CERTIFIED_DASHBOARD_TEMPLATE = "portal/staff/director_dashboard.html"
_SAFE_PREFIX = re.compile(r"^[a-z][a-z0-9-]*$")


@dataclass(frozen=True, slots=True)
class CertifiedDashboardShell:
    role: str
    key: str
    page_title: str
    title: str
    subtitle: str
    context_label: str
    user_name: str
    navigation: list
    active_section: str
    workspace_template: str
    topbar_template: str
    script_path: str
    stylesheet_path: str
    notifications_url: str
    show_notifications_button: bool
    drawer_title: str
    modal_title: str
    empty_drawer_message: str
    empty_modal_message: str

    @property
    def workspace_id(self):
        return f"{self.key}-workspace"

    @property
    def loading_id(self):
        return f"{self.key}-loading"

    @property
    def drawer_id(self):
        return f"{self.key}-drawer"

    @property
    def modal_id(self):
        return f"{self.key}-modal"

    @property
    def confirm_id(self):
        return f"{self.key}-confirm"

    def as_template_context(self):
        payload = asdict(self)
        payload.update(
            {
                "workspace_id": self.workspace_id,
                "loading_id": self.loading_id,
                "drawer_id": self.drawer_id,
                "modal_id": self.modal_id,
                "confirm_id": self.confirm_id,
                "certified_template": CERTIFIED_DASHBOARD_TEMPLATE,
            }
        )
        return payload


def build_certified_dashboard_shell(
    *,
    role,
    key,
    page_title,
    title,
    subtitle,
    context_label,
    user_name,
    navigation,
    active_section,
    workspace_template,
    topbar_template,
    script_path,
    stylesheet_path="",
    notifications_url="",
    show_notifications_button=False,
    drawer_title="Détail",
    modal_title="Gestion",
    empty_drawer_message="Sélectionnez un élément pour afficher ses détails.",
    empty_modal_message="Sélectionnez une action pour ouvrir le formulaire.",
):
    """Return the normalized context for the certified DE dashboard shell."""

    normalized_key = str(key or "").strip().lower()
    if not _SAFE_PREFIX.fullmatch(normalized_key):
        raise ValueError("La clé du dashboard doit être un préfixe HTML sûr.")
    if not workspace_template or not topbar_template:
        raise ValueError("Le workspace et la topbar du dashboard sont obligatoires.")

    shell = CertifiedDashboardShell(
        role=str(role or "").strip(),
        key=normalized_key,
        page_title=str(page_title or title).strip(),
        title=str(title).strip(),
        subtitle=str(subtitle or title).strip(),
        context_label=str(context_label or "").strip(),
        user_name=str(user_name or "").strip(),
        navigation=list(navigation or []),
        active_section=str(active_section or "home").strip(),
        workspace_template=str(workspace_template).strip(),
        topbar_template=str(topbar_template).strip(),
        script_path=str(script_path or "").strip(),
        stylesheet_path=str(stylesheet_path or "").strip(),
        notifications_url=str(notifications_url or "").strip(),
        show_notifications_button=bool(show_notifications_button),
        drawer_title=str(drawer_title).strip(),
        modal_title=str(modal_title).strip(),
        empty_drawer_message=str(empty_drawer_message).strip(),
        empty_modal_message=str(empty_modal_message).strip(),
    )
    return {
        "dashboard_shell": shell.as_template_context(),
        # The certified shell owns its notification bell in the topbar. The
        # global floating widget would otherwise render a second entry point.
        "suppress_portal_notification_component": True,
    }


def build_certified_navigation(
    *,
    groups,
    active_section,
    dashboard_url,
    workspace_target="",
):
    """Normalize role-owned links for the certified UI Core sidebar.

    Access decisions remain in the view/policy layer.  This helper only turns
    the modules already authorized by that layer into the presentation shape
    consumed by ``ui_core.app_sidebar``.
    """

    navigation = []
    for group in groups or []:
        items = []
        for source in group.get("items", []):
            item = dict(source)
            section = str(item.pop("key", item.get("nav_key", "")) or "").strip()
            url = item.pop("url", "")
            if not url:
                query = urlencode({"section": section}) if section else ""
                url = f"{dashboard_url}?{query}" if query else dashboard_url
            hx_get = item.pop("hx_get", "")
            target = item.pop("hx_target", "") or (workspace_target if hx_get else "")
            items.append(
                {
                    "label": item.pop("label", section.replace("_", " ").title()),
                    "url": url,
                    "icon": item.pop("icon", "circle"),
                    "active": bool(item.pop("active", section == active_section)),
                    "badge": item.pop("badge", None),
                    "disabled": bool(item.pop("disabled", False)),
                    "hx_get": hx_get,
                    "hx_target": target,
                    "hx_swap": item.pop("hx_swap", "innerHTML" if hx_get else ""),
                    "hx_push_url": item.pop("hx_push_url", url if hx_get else ""),
                    "nav_key": item.pop("nav_key", section),
                }
            )
        if items:
            navigation.append({"label": group.get("label", "Navigation"), "items": items})
    return navigation


def build_role_dashboard_shell(
    request,
    *,
    role,
    key,
    title,
    subtitle,
    active_section,
    groups,
    dashboard_url="",
    workspace_template="portal/staff/shared/empty_workspace.html",
    workspace_target="",
    branch=None,
    context_label="",
    page_title="",
    topbar_template="portal/staff/shared/topbar_actions.html",
    script_path="",
    stylesheet_path="",
    drawer_title="Detail",
    modal_title="Gestion",
):
    """Build the common DE shell plus the scoped context for one role."""

    dashboard_url = dashboard_url or request.path
    scope = get_user_scope(request.user)
    scoped_branch = branch if branch is not None else scope.get("branch")
    if not context_label:
        if scope.get("is_global"):
            context_label = "Vue globale - Toutes les annexes"
        elif scoped_branch is not None:
            context_label = f"Annexe - {scoped_branch.name}"
        else:
            context_label = "Perimetre du compte"

    navigation = build_certified_navigation(
        groups=groups,
        active_section=active_section,
        dashboard_url=dashboard_url,
        workspace_target=workspace_target,
    )
    try:
        notification_count = get_user_unread_count(request.user)
    except (OperationalError, ProgrammingError):
        notification_count = 0

    context = build_certified_dashboard_shell(
        role=role,
        key=key,
        page_title=page_title or f"{title} - ESFE",
        title=title,
        subtitle=subtitle,
        context_label=context_label,
        user_name=request.user.get_full_name() or request.user.username,
        navigation=navigation,
        active_section=active_section,
        workspace_template=workspace_template,
        topbar_template=topbar_template,
        script_path=script_path,
        stylesheet_path=stylesheet_path,
        notifications_url=reverse("notification_center:notifications"),
        show_notifications_button=True,
        drawer_title=drawer_title,
        modal_title=modal_title,
    )
    context.update(
        {
            "page_title": page_title or f"{title} - ESFE",
            "notification_count": notification_count,
            # Legacy bases can use a variable parent during their progressive
            # migration while still inheriting the one certified DE shell.
            "dashboard_parent": CERTIFIED_DASHBOARD_TEMPLATE,
        }
    )
    return context
