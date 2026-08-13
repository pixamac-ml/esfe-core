from django.test import SimpleTestCase

from portal.services.certified_dashboard_shell import (
    CERTIFIED_DASHBOARD_TEMPLATE,
    build_certified_dashboard_shell,
)


class CertifiedDashboardShellContractTests(SimpleTestCase):
    def _build(self, **overrides):
        values = {
            "role": "academic_supervisor",
            "key": "supervisor",
            "page_title": "Dashboard Surveillant General",
            "title": "Surveillance générale",
            "subtitle": "Surveillance générale",
            "context_label": "Annexe A",
            "user_name": "Utilisateur Test",
            "navigation": [{"label": "Pilotage", "items": []}],
            "active_section": "home",
            "workspace_template": "portal/staff/supervisor/partials/workflow_workspace.html",
            "topbar_template": "portal/staff/supervisor/partials/topbar_actions.html",
            "script_path": "src/js/portal/supervisor_dashboard.js",
        }
        values.update(overrides)
        return build_certified_dashboard_shell(**values)

    def test_contract_derives_stable_ui_ids_from_role_key(self):
        context = self._build()
        shell = context["dashboard_shell"]

        self.assertEqual(shell["certified_template"], CERTIFIED_DASHBOARD_TEMPLATE)
        self.assertTrue(context["suppress_portal_notification_component"])
        self.assertEqual(shell["workspace_id"], "supervisor-workspace")
        self.assertEqual(shell["loading_id"], "supervisor-loading")
        self.assertEqual(shell["drawer_id"], "supervisor-drawer")
        self.assertEqual(shell["modal_id"], "supervisor-modal")
        self.assertEqual(shell["confirm_id"], "supervisor-confirm")

    def test_contract_rejects_unsafe_html_prefix(self):
        with self.assertRaises(ValueError):
            self._build(key="Supervisor workspace")

    def test_contract_requires_workspace_and_topbar_fragments(self):
        with self.assertRaises(ValueError):
            self._build(workspace_template="")
        with self.assertRaises(ValueError):
            self._build(topbar_template="")
