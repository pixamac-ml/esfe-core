"""Registry mapping certified dashboard keys to their entry points.

The certified dashboard shell derives every HTMX target id (workspace,
drawer, modal) from the dashboard key, so the generic staff endpoints only
need the key plus the dashboard URL used for history push.
"""

from django.urls import reverse


STAFF_DASHBOARDS = {
    "manager": {"url_name": "accounts_portal:portal_annex_manager"},
    "supervisor": {"url_name": "accounts_portal:portal_dashboard"},
    "sg": {"url_name": "secretary:secretary_dashboard"},
    "it-dashboard": {"url_name": "accounts_portal:portal_dashboard"},
    "teacher": {"url_name": "accounts_portal:portal_teacher"},
    "executive": {"url_name": "accounts_portal:portal_dg"},
    "marketing": {"url_name": "marketing:dashboard"},
    "superadmin": {"url_name": "superadmin:dashboard"},
}


class StaffDashboardTarget:
    """Resolve the HTMX anchors of one certified dashboard from its key."""

    def __init__(self, key, url_name):
        self.key = key
        self.url_name = url_name

    @property
    def dashboard_url(self):
        return reverse(self.url_name)

    @property
    def workspace_target(self):
        return f"#{self.key}-workspace"

    @property
    def drawer_content_target(self):
        return f"#{self.key}-drawer-content"

    @property
    def modal_content_target(self):
        return f"#{self.key}-modal-content"

    @property
    def drawer_id(self):
        return f"{self.key}-drawer"

    @property
    def modal_id(self):
        return f"{self.key}-modal"


def resolve_staff_dashboard(dash_key):
    key = str(dash_key or "").strip().lower()
    entry = STAFF_DASHBOARDS.get(key)
    if entry is None:
        return None
    return StaffDashboardTarget(key, entry["url_name"])
