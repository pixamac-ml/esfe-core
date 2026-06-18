"""Tests pour le telechargement securise des fiches de paie / honoraires."""

from datetime import date
from decimal import Decimal
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from branches.models import Branch
from accounts.models import PayrollEntry, TeacherHonorariumEntry


User = get_user_model()
USER_MANAGER = cast(Any, User._default_manager)


def _create_user(username, branch=None, position="secretary", **kw):
    user = USER_MANAGER.create_user(
        username=username, email=f"{username}@test.com", password="pass1234", **kw,
    )
    if branch:
        profile = user.profile
        profile.branch = branch
        profile.position = position
        profile.save(update_fields=["branch", "position", "updated_at"])
    return user


def _create_branch(code="PDF", name="Annexe PDF"):
    return Branch.objects.create(name=name, code=code, slug=f"annexe-{code.lower()}")


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class PayslipDownloadTests(TestCase):
    """Telechargement de la fiche de paie (PayrollEntry)."""

    def setUp(self):
        self.branch = _create_branch()
        self.employee = _create_user("payslip_owner", branch=self.branch)
        self.other = _create_user("payslip_other", branch=self.branch)
        self.entry = PayrollEntry.objects.create(
            branch=self.branch,
            employee=self.employee,
            period_month=date.today().replace(day=1),
            base_salary=300000,
            allowances=20000,
            deductions=5000,
            advances=10000,
            paid_amount=50000,
        )

    def test_owner_can_download_pdf(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse("accounts:payslip_download", args=[self.entry.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])

    def test_other_user_gets_404(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse("accounts:payslip_download", args=[self.entry.id]))
        self.assertEqual(response.status_code, 404)

    def test_anonymous_user_redirected_to_login(self):
        response = self.client.get(reverse("accounts:payslip_download", args=[self.entry.id]))
        self.assertEqual(response.status_code, 302)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class HonorariumDownloadTests(TestCase):
    """Telechargement du bordereau d'honoraires (TeacherHonorariumEntry)."""

    def setUp(self):
        self.branch = _create_branch(code="PDH", name="Annexe PDF Honoraires")
        self.teacher = _create_user("honorarium_owner", branch=self.branch, position="teacher")
        self.other = _create_user("honorarium_other", branch=self.branch, position="teacher")
        self.entry = TeacherHonorariumEntry.objects.create(
            branch=self.branch,
            teacher=self.teacher,
            period_month=date.today().replace(day=1),
            hourly_rate=5000,
            validated_hours=Decimal("40"),
            adjustments=10000,
            deductions=5000,
            paid_amount=20000,
        )

    def test_owner_can_download_pdf(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("accounts:honorarium_download", args=[self.entry.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])

    def test_other_user_gets_404(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse("accounts:honorarium_download", args=[self.entry.id]))
        self.assertEqual(response.status_code, 404)
