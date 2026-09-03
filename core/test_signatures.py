"""Tests du socle de signature réutilisable."""

import base64
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from branches.models import Branch
from core.models import SignatureRequest
from core.services.signatures import (
    approve_signature,
    capture_signature,
    get_signature_request,
    get_signed_signature_for_subject,
    request_signature,
)
from students.services.attendance_workflow import start_daily_roll
from django.core.exceptions import ValidationError
from django.utils import timezone


User = get_user_model()


class SignatureServiceTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name="Annexe signatures", code="SIG", slug="annexe-signatures"
        )
        self.teacher = User.objects.create_user("signature_teacher", password="test-password")
        self.supervisor = User.objects.create_user("signature_supervisor", password="test-password")
        self.snapshot = {"document": "cahier", "content": "Suite et limites", "version": 1}

    def _new_request(self):
        return request_signature(
            branch=self.branch,
            purpose=SignatureRequest.PURPOSE_LESSON_LOG,
            subject=self.branch,
            signer=self.teacher,
            requested_by=self.teacher,
            title="Cahier de texte",
            snapshot=self.snapshot,
        )

    def test_signature_is_bound_to_its_snapshot_then_approved(self):
        signature_request = self._new_request()
        request = RequestFactory().post("/signature/", REMOTE_ADDR="127.0.0.1")
        signature_data = "data:image/png;base64," + base64.b64encode(b"ink").decode()

        capture_signature(
            signature_request=signature_request,
            signature_data=signature_data,
            request=request,
        )
        signature_request.refresh_from_db()
        self.assertEqual(signature_request.status, SignatureRequest.STATUS_SIGNED)
        self.assertTrue(signature_request.signature_sha256)

        signed = get_signed_signature_for_subject(
            branch=self.branch,
            purpose=SignatureRequest.PURPOSE_LESSON_LOG,
            subject=self.branch,
            signer=self.teacher,
            snapshot=self.snapshot,
        )
        self.assertEqual(signed, signature_request)
        self.assertIsNone(
            get_signed_signature_for_subject(
                branch=self.branch,
                purpose=SignatureRequest.PURPOSE_LESSON_LOG,
                subject=self.branch,
                signer=self.teacher,
                snapshot={**self.snapshot, "content": "modifié"},
            )
        )

        approve_signature(signature_request=signature_request, approver=self.supervisor)
        signature_request.refresh_from_db()
        self.assertEqual(signature_request.status, SignatureRequest.STATUS_APPROVED)
        self.assertEqual(signature_request.approved_by, self.supervisor)

    def test_new_request_cancels_previous_active_request(self):
        first = self._new_request()
        second = self._new_request()

        first.refresh_from_db()
        self.assertEqual(first.status, SignatureRequest.STATUS_CANCELLED)
        self.assertEqual(second.status, SignatureRequest.STATUS_AWAITING_SIGNATURE)
        self.assertEqual(get_signature_request(raw_token=second.raw_token), second)

    def test_only_an_unsigned_request_expires(self):
        signature_request = self._new_request()
        signature_request.expires_at = timezone.now() - timedelta(seconds=1)
        signature_request.save(update_fields=["expires_at"])

        expired = get_signature_request(raw_token=signature_request.raw_token)
        self.assertEqual(expired.status, SignatureRequest.STATUS_EXPIRED)

        signed_request = self._new_request()
        capture_signature(
            signature_request=signed_request,
            signature_data="data:image/png;base64," + base64.b64encode(b"ink").decode(),
            request=RequestFactory().post("/signature/"),
        )
        signed_request.expires_at = timezone.now() - timedelta(seconds=1)
        signed_request.save(update_fields=["expires_at"])
        self.assertEqual(
            get_signature_request(raw_token=signed_request.raw_token).status,
            SignatureRequest.STATUS_SIGNED,
        )

    def test_future_attendance_roll_is_rejected_before_any_write(self):
        with self.assertRaisesMessage(ValidationError, "avant le jour de la séance"):
            start_daily_roll(
                user=self.supervisor,
                branch=self.branch,
                academic_class_id=0,
                roll_date=timezone.localdate() + timedelta(days=1),
            )
