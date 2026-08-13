from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from accounts.services.manager_workspace_access import resolve_manager_workspace_access


@override_settings(AUTH_POLICY_V2_ENABLED=False)
class ManagerWorkspaceAccessTests(SimpleTestCase):
    def _user(self):
        return SimpleNamespace(is_authenticated=True)

    @patch("accounts.services.manager_workspace_access.get_user_branch")
    @patch("accounts.services.manager_workspace_access.is_manager")
    @patch("accounts.services.manager_workspace_access.get_user_position")
    def test_manager_receives_every_section(self, position, is_manager, branch):
        position.return_value = "annex_manager"
        is_manager.return_value = True
        branch.return_value = object()

        access = resolve_manager_workspace_access(self._user())

        self.assertIn("paiements", access.allowed_sections)
        self.assertIn("salaires", access.allowed_sections)
        self.assertTrue(access.can("manage_all_manager_modules"))

    @patch("accounts.services.manager_workspace_access.get_user_branch")
    @patch("accounts.services.manager_workspace_access.check_finance_access")
    @patch("accounts.services.manager_workspace_access.get_user_position")
    def test_finance_manager_is_restricted_to_finance_context(self, position, check_finance, branch):
        position.return_value = "finance_manager"
        check_finance.return_value = True
        branch.return_value = object()

        access = resolve_manager_workspace_access(self._user())

        self.assertEqual(access.default_section, "paiements")
        self.assertEqual(access.allowed_sections, {"paiements", "settings"})
        self.assertTrue(access.can("correct_payment"))
        self.assertFalse(access.can("manage_all_manager_modules"))

    @patch("accounts.services.manager_workspace_access.get_user_branch")
    @patch("accounts.services.manager_workspace_access.check_finance_access")
    @patch("accounts.services.manager_workspace_access.get_user_position")
    def test_payment_agent_cannot_correct_validated_payment(self, position, check_finance, branch):
        position.return_value = "payment_agent"
        check_finance.return_value = True
        branch.return_value = object()

        access = resolve_manager_workspace_access(self._user())

        self.assertTrue(access.can("validate_payment"))
        self.assertTrue(access.can("manage_cash_sessions"))
        self.assertFalse(access.can("correct_payment"))

    @patch("accounts.services.manager_workspace_access.get_user_branch")
    @patch("accounts.services.manager_workspace_access.get_user_position")
    def test_admissions_receives_only_admission_sections(self, position, branch):
        position.return_value = "admissions"
        branch.return_value = object()

        access = resolve_manager_workspace_access(self._user())

        self.assertEqual(access.default_section, "candidatures")
        self.assertEqual(access.allowed_sections, {"candidatures", "inscriptions", "settings"})
        self.assertTrue(access.can("manage_admissions"))
        self.assertTrue(access.can("create_inscription"))
        self.assertFalse(access.can("validate_payment"))

    @patch("accounts.services.manager_workspace_access.get_user_branch", return_value=None)
    @patch("accounts.services.manager_workspace_access.get_user_position", return_value="finance_manager")
    def test_branch_is_mandatory(self, _position, _branch):
        self.assertIsNone(resolve_manager_workspace_access(self._user()))
