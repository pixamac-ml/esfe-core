from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from portal.dg.context import MODE_BRANCH, MODE_GLOBAL, SESSION_KEY, resolve_dg_context
from portal.dg.forms import DgStaffLifecycleForm
from portal.dg.services import _event_status


class DgDashboardContextResolverUnitTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.current_year = SimpleNamespace(id=7, name="2032-2033", is_active=True)
        self.archived_year = SimpleNamespace(id=6, name="2031-2032", is_active=False)
        self.centre = SimpleNamespace(id=11, name="Centre")
        self.nord = SimpleNamespace(id=12, name="Nord")

    def _resolve(self, request):
        with patch(
            "portal.dg.context.AcademicYear.objects.order_by",
            return_value=[self.current_year, self.archived_year],
        ), patch("portal.dg.context.get_active_branches", return_value=[self.centre, self.nord]):
            return resolve_dg_context(request)

    def test_query_parameters_take_precedence_and_are_persisted(self):
        request = self.factory.get("/portal/dg/", {"academic_year_id": "6", "branch_id": "12"})
        request.session = {}

        context = self._resolve(request)

        self.assertEqual(context.academic_year, self.archived_year)
        self.assertEqual(context.selected_branch, self.nord)
        self.assertEqual(context.mode, MODE_BRANCH)
        self.assertEqual(
            request.session[SESSION_KEY],
            {"academic_year_id": 6, "branch_id": 12, "mode": MODE_BRANCH},
        )

    def test_saved_context_is_restored_and_empty_branch_switches_global(self):
        request = self.factory.get("/portal/dg/")
        request.session = {
            SESSION_KEY: {"academic_year_id": 6, "branch_id": 11, "mode": MODE_BRANCH}
        }

        restored = self._resolve(request)
        self.assertEqual(restored.academic_year, self.archived_year)
        self.assertEqual(restored.selected_branch, self.centre)

        global_request = self.factory.get("/portal/dg/", {"branch_id": ""})
        global_request.session = request.session
        global_context = self._resolve(global_request)
        self.assertIsNone(global_context.selected_branch)
        self.assertEqual(global_context.mode, MODE_GLOBAL)
        self.assertEqual(global_request.session[SESSION_KEY]["branch_id"], None)

    def test_invalid_identifiers_fall_back_to_safe_global_active_context(self):
        request = self.factory.get("/portal/dg/", {"academic_year_id": "999", "branch_id": "999"})
        request.session = {}

        context = self._resolve(request)

        self.assertEqual(context.academic_year, self.current_year)
        self.assertIsNone(context.selected_branch)
        self.assertEqual(context.mode, MODE_GLOBAL)

    def test_sensitive_staff_actions_require_a_reason(self):
        form = DgStaffLifecycleForm({"profile_id": "1", "action": "suspend", "reason": ""})

        self.assertFalse(form.is_valid())
        self.assertIn("reason", form.errors)

    def test_schedule_status_accepts_serialized_and_orm_events(self):
        self.assertEqual(_event_status({"status": "cancelled"}), "cancelled")
        self.assertEqual(_event_status(SimpleNamespace(status="planned")), "planned")
