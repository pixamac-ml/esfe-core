from django.test import TestCase

from academic_cycle.permissions import can_close_branch_cycle


class PermissionSmokeTests(TestCase):
    def test_anonymous_cannot_close(self):
        self.assertFalse(can_close_branch_cycle(None, None))
