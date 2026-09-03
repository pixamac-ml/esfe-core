import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from branches.models import Branch
from core.services.business_data_reset import (
    assert_safe_local_development_database,
    remaining_business_data,
    reset_business_data,
)
from core.services.institution_bootstrap import (
    apply_bootstrap_manifest,
    load_bootstrap_manifest,
)


class BusinessDataResetTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin = user_model.objects.create_superuser(
            username="reset-admin",
            email="reset-admin@example.com",
            password="reset-password",
        )
        self.director = user_model.objects.create_user(
            username="reset-director",
            email="reset-director@example.com",
            password="reset-password",
            is_staff=True,
        )
        self.demo_user = user_model.objects.create_user(
            username="reset-demo",
            password="reset-password",
        )
        Branch.objects.create(name="Annexe de test", code="RST", slug="annexe-reset")

    def test_reset_preserves_selected_accounts_and_is_idempotent(self):
        summary = reset_business_data(
            preserve_usernames=(self.admin.username, self.director.username)
        )

        user_model = get_user_model()
        self.assertEqual(
            set(user_model.objects.values_list("username", flat=True)),
            {self.admin.username, self.director.username},
        )
        self.assertFalse(
            user_model.objects.filter(username=self.demo_user.username).exists()
        )
        self.assertEqual(Branch.objects.count(), 0)
        self.assertGreater(summary.deleted_total, 0)
        self.assertEqual(
            remaining_business_data(user_model.objects.values_list("id", flat=True)),
            {},
        )

        second_summary = reset_business_data(
            preserve_usernames=(self.admin.username, self.director.username)
        )
        self.assertEqual(second_summary.deleted_total, 0)

    @override_settings(DEBUG=False)
    def test_reset_refuses_non_debug_environment(self):
        with self.assertRaisesMessage(CommandError, "DEBUG doit être activé"):
            assert_safe_local_development_database()


class InstitutionBootstrapTests(TestCase):
    def test_empty_versioned_manifest_is_valid(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "institution.json"
            path.write_text(json.dumps({"version": 1, "objects": []}), encoding="utf-8")

            payload = load_bootstrap_manifest(path)
            summary = apply_bootstrap_manifest(payload)

        self.assertEqual(summary.created, 0)
        self.assertEqual(summary.updated, 0)

    def test_manifest_upserts_structural_data_idempotently(self):
        payload = {
            "version": 1,
            "objects": [
                {
                    "id": "branch.test",
                    "model": "branches.Branch",
                    "lookup": {"code": "BTST"},
                    "fields": {"name": "Annexe bootstrap", "slug": "annexe-bootstrap"},
                }
            ],
        }

        first = apply_bootstrap_manifest(payload)
        second = apply_bootstrap_manifest(payload)

        self.assertEqual(first.created, 1)
        self.assertEqual(second.updated, 1)
        self.assertEqual(Branch.objects.filter(code="BTST").count(), 1)

    def test_dry_run_rolls_back_and_forbidden_model_is_rejected(self):
        payload = {
            "version": 1,
            "objects": [
                {
                    "model": "branches.Branch",
                    "lookup": {"code": "DRY"},
                    "fields": {"name": "Dry run", "slug": "dry-run"},
                }
            ],
        }
        apply_bootstrap_manifest(payload, dry_run=True)
        self.assertFalse(Branch.objects.filter(code="DRY").exists())

        payload["objects"][0]["model"] = "auth.User"
        with self.assertRaisesMessage(CommandError, "Modèle de bootstrap interdit"):
            apply_bootstrap_manifest(payload)

    def test_bootstrap_command_accepts_the_empty_repository_manifest(self):
        call_command("bootstrap_institution", dry_run=True, verbosity=0)
