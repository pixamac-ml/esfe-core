"""Reusable handwritten-signature evidence for ESFE workflows."""

import base64
import hashlib
import json
import re
from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import SignatureRequest


DEFAULT_SIGNATURE_LIFETIME = timedelta(minutes=30)
_DATA_IMAGE_RE = re.compile(r"^data:image/(?:png|jpeg);base64,[A-Za-z0-9+/=\s]+$")


def canonical_snapshot_digest(snapshot):
    """Return a stable hash for the exact business data being signed."""

    serialized = json.dumps(
        snapshot or {},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@transaction.atomic
def request_signature(*, branch, purpose, subject, signer, requested_by, title, snapshot, lifetime=None):
    """Create one fresh signature request for a frozen business snapshot."""

    if branch is None or getattr(subject, "pk", None) is None or signer is None:
        raise ValidationError("Annexe, document et signataire sont obligatoires.")
    if not signer.is_active:
        raise ValidationError("Le compte du signataire n'est pas actif.")
    if purpose not in dict(SignatureRequest.PURPOSE_CHOICES):
        raise ValidationError("Type de signature invalide.")

    content_type = ContentType.objects.get_for_model(subject, for_concrete_model=False)
    SignatureRequest.objects.filter(
        branch=branch,
        purpose=purpose,
        content_type=content_type,
        object_id=subject.pk,
        signer=signer,
        status__in=SignatureRequest.ACTIVE_STATUSES,
    ).update(status=SignatureRequest.STATUS_CANCELLED)

    raw_token, token_hash = SignatureRequest.issue_token()
    request = SignatureRequest.objects.create(
        branch=branch,
        purpose=purpose,
        content_type=content_type,
        object_id=subject.pk,
        signer=signer,
        requested_by=requested_by,
        title=(title or "Document ESFE")[:255],
        snapshot=snapshot or {},
        document_digest=canonical_snapshot_digest(snapshot),
        token_hash=token_hash,
        expires_at=timezone.now() + (lifetime or DEFAULT_SIGNATURE_LIFETIME),
    )
    request.raw_token = raw_token
    return request


def get_signature_request(*, raw_token, signer=None):
    request = (
        SignatureRequest.objects.select_related("branch", "signer", "requested_by", "content_type")
        .filter(token_hash=SignatureRequest.hash_token(raw_token))
        .first()
    )
    if request is None:
        raise ValidationError("Demande de signature introuvable.")
    if signer is not None and request.signer_id != signer.id:
        raise ValidationError("Cette demande de signature ne vous appartient pas.")
    if request.status == SignatureRequest.STATUS_AWAITING_SIGNATURE and request.is_expired:
        request.status = SignatureRequest.STATUS_EXPIRED
        request.save(update_fields=["status", "updated_at"])
    return request


@transaction.atomic
def capture_signature(*, signature_request, signature_data, request):
    """Store the handwritten signature and its audit metadata exactly once."""

    if signature_request.status != SignatureRequest.STATUS_AWAITING_SIGNATURE or signature_request.is_expired:
        raise ValidationError("Cette demande de signature n'est plus utilisable.")
    if not signature_data or len(signature_data) > 350000 or not _DATA_IMAGE_RE.match(signature_data):
        raise ValidationError("La signature tablette est invalide ou trop volumineuse.")
    try:
        base64.b64decode(signature_data.split(",", 1)[1], validate=True)
    except (ValueError, UnicodeEncodeError):
        raise ValidationError("La signature tablette est invalide.")

    signature_request.signature_data = signature_data
    signature_request.signature_sha256 = hashlib.sha256(signature_data.encode("utf-8")).hexdigest()
    signature_request.signed_at = timezone.now()
    signature_request.signed_ip = request.META.get("REMOTE_ADDR")
    signature_request.signed_user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:300]
    signature_request.status = SignatureRequest.STATUS_SIGNED
    signature_request.save(
        update_fields=[
            "signature_data",
            "signature_sha256",
            "signed_at",
            "signed_ip",
            "signed_user_agent",
            "status",
            "updated_at",
        ]
    )
    return signature_request


def get_signed_signature_for_subject(*, branch, purpose, subject, signer, snapshot):
    """Return a valid signed proof only when it matches the current snapshot."""

    content_type = ContentType.objects.get_for_model(subject, for_concrete_model=False)
    return (
        SignatureRequest.objects.filter(
            branch=branch,
            purpose=purpose,
            content_type=content_type,
            object_id=subject.pk,
            signer=signer,
            status__in=(SignatureRequest.STATUS_SIGNED, SignatureRequest.STATUS_APPROVED),
            document_digest=canonical_snapshot_digest(snapshot),
        )
        .order_by("-signed_at", "-id")
        .first()
    )


@transaction.atomic
def approve_signature(*, signature_request, approver):
    if signature_request.status != SignatureRequest.STATUS_SIGNED:
        raise ValidationError("La signature doit être recue avant approbation.")
    signature_request.status = SignatureRequest.STATUS_APPROVED
    signature_request.approved_by = approver
    signature_request.approved_at = timezone.now()
    signature_request.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    return signature_request
