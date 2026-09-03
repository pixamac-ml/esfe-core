"""Tests HTTP 200 pour chaque section du portail enseignant (HTMX + page entière).

Critères CLAUDE-3 :
- 8 sections accessibles via HTMX (HX-Request) → HTTP 200
- Page entière (sans HX-Request) → HTTP 200
- Aucune section ne lève d'exception avec un enseignant sans données associées
"""
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Profile
from branches.models import Branch


User = get_user_model()
USER_MANAGER = cast(Any, User._default_manager)

PORTAL_TEACHER_URL_NAME = "accounts_portal:portal_teacher"

TEACHER_SECTIONS = (
    "overview",
    "classes",
    "supports",
    "evaluations",
    "schedule",
    "logs",
    "salary",
    "notifications",
    "settings",
)


def _create_branch(code="TTC", name="Annexe Tests Enseignant"):
    return Branch.objects.create(name=name, code=code, slug=f"annexe-{code.lower()}")


def _create_teacher(branch, username="teacher_test_user"):
    user = USER_MANAGER.create_user(
        username=username,
        password="test_pass_123!",
        first_name="Enseignant",
        last_name="Test",
    )
    Profile.objects.filter(user=user).update(
        role="teacher",
        position="teacher",
        branch=branch,
        user_type="staff",
    )
    return user


class TeacherPortalSectionTests(TestCase):
    """Vérifie que chaque section du portail enseignant renvoie HTTP 200."""

    @classmethod
    def setUpTestData(cls):
        cls.branch = _create_branch()
        cls.teacher = _create_teacher(cls.branch)
        cls.url = reverse(PORTAL_TEACHER_URL_NAME)

    def setUp(self):
        self.client.force_login(self.teacher)

    def _get_section_htmx(self, section):
        return self.client.get(
            self.url,
            {"section": section},
            HTTP_HX_REQUEST="true",
        )

    def test_full_page_overview(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_htmx_overview(self):
        self.assertEqual(self._get_section_htmx("overview").status_code, 200)

    def test_htmx_classes(self):
        self.assertEqual(self._get_section_htmx("classes").status_code, 200)

    def test_htmx_supports(self):
        self.assertEqual(self._get_section_htmx("supports").status_code, 200)

    def test_htmx_evaluations(self):
        self.assertEqual(self._get_section_htmx("evaluations").status_code, 200)

    def test_htmx_schedule(self):
        self.assertEqual(self._get_section_htmx("schedule").status_code, 200)

    def test_htmx_logs(self):
        self.assertEqual(self._get_section_htmx("logs").status_code, 200)

    def test_htmx_salary(self):
        self.assertEqual(self._get_section_htmx("salary").status_code, 200)

    def test_htmx_notifications(self):
        self.assertEqual(self._get_section_htmx("notifications").status_code, 200)

    def test_htmx_settings(self):
        self.assertEqual(self._get_section_htmx("settings").status_code, 200)

    def test_htmx_invalid_section_falls_back_to_overview(self):
        response = self._get_section_htmx("does_not_exist")
        self.assertEqual(response.status_code, 200)

    def test_full_page_each_section(self):
        for section in TEACHER_SECTIONS:
            with self.subTest(section=section):
                response = self.client.get(self.url, {"section": section})
                self.assertEqual(
                    response.status_code,
                    200,
                    msg=f"Section '{section}' a renvoyé {response.status_code} (attendu 200)",
                )

    def test_unauthenticated_redirects(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertIn(response.status_code, (302, 403))

    def test_branch_missing_shows_dashboard_without_error(self):
        user_no_branch = USER_MANAGER.create_user(
            username="teacher_no_branch",
            password="test_pass_123!",
        )
        Profile.objects.filter(user=user_no_branch).update(
            role="teacher",
            position="teacher",
            branch=None,
            user_type="staff",
        )
        self.client.force_login(user_no_branch)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"teacher-workspace", response.content)
