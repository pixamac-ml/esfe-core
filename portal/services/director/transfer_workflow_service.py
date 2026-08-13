import re

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from academics.models import AcademicClass, AcademicEnrollment
from accounts.dashboards.helpers import get_user_branch
from admissions.models import Candidature
from portal.models import (
    IncomingTransfer,
    InternalTransfer,
    OutgoingTransfer,
    TransferDecision,
    TransferDocument,
    TransferHistory,
    TransferRequest,
    TransferSchool,
)


ACTIVE_TRANSFER_STATUSES = (
    TransferRequest.STATUS_SUBMITTED,
    TransferRequest.STATUS_UNDER_REVIEW,
    TransferRequest.STATUS_AWAITING_DOCUMENTS,
    TransferRequest.STATUS_APPROVED,
    TransferRequest.STATUS_HANDOVER,
)


def _student_label(enrollment):
    if enrollment is None:
        return ""
    return enrollment.student.get_full_name() or enrollment.student.username


def _source_snapshot(enrollment):
    if enrollment is None:
        return {}
    return {
        "enrollment_id": enrollment.pk,
        "student_id": enrollment.student_id,
        "student": _student_label(enrollment),
        "inscription_id": enrollment.inscription_id,
        "programme_id": enrollment.programme_id,
        "programme": str(enrollment.programme),
        "class_id": enrollment.academic_class_id,
        "class": enrollment.academic_class.display_name,
        "level": enrollment.academic_class.level,
        "academic_year_id": enrollment.academic_year_id,
        "academic_year": str(enrollment.academic_year),
        "branch_id": enrollment.branch_id,
    }


def _log(transfer, *, actor, action, from_status="", to_status="", note="", snapshot=None):
    return TransferHistory.objects.create(
        transfer_request=transfer,
        actor=actor,
        action=action,
        from_status=from_status,
        to_status=to_status,
        note=(note or "").strip(),
        snapshot=snapshot or {},
    )


def _set_status(transfer, *, actor, status, action, note=""):
    old_status = transfer.status
    transfer.status = status
    transfer.reviewed_by = actor
    transfer.reviewed_at = timezone.now()
    fields = ["status", "reviewed_by", "reviewed_at", "updated_at"]
    if status == TransferRequest.STATUS_COMPLETED:
        transfer.completed_at = timezone.now()
        fields.append("completed_at")
    transfer.save(update_fields=fields)
    _log(
        transfer,
        actor=actor,
        action=action,
        from_status=old_status,
        to_status=status,
        note=note,
    )


def build_director_transfer_context(*, branch, scope="overview", query="", transfer_type=""):
    enrollments = list(
        AcademicEnrollment.objects.select_related(
            "academic_class", "academic_class__programme", "student", "programme", "academic_year"
        )
        .filter(branch=branch, is_active=True, is_archived=False)
        .order_by("academic_class__level", "student__last_name", "student__first_name")[:300]
    ) if branch else []
    transfers = (
        TransferRequest.objects.select_related(
            "enrollment", "enrollment__student", "source_class", "target_class",
            "created_by", "reviewed_by", "internal_details", "outgoing_details",
            "outgoing_details__destination_school", "incoming_details",
            "incoming_details__origin_school", "incoming_details__candidature",
        ).prefetch_related("documents", "history").filter(branch=branch)
    ) if branch else TransferRequest.objects.none()
    all_transfers = transfers
    query = (query or "").strip()
    if query:
        transfers = transfers.filter(
            Q(enrollment__student__first_name__icontains=query)
            | Q(enrollment__student__last_name__icontains=query)
            | Q(enrollment__student__username__icontains=query)
            | Q(incoming_details__first_name__icontains=query)
            | Q(incoming_details__last_name__icontains=query)
            | Q(source_class__name__icontains=query)
            | Q(target_class__name__icontains=query)
            | Q(target_school_name__icontains=query)
            | Q(reference__icontains=query)
        ).distinct()
    if transfer_type in dict(TransferRequest.TYPE_CHOICES):
        transfers = transfers.filter(transfer_type=transfer_type)
    if scope == "pending":
        transfers = transfers.filter(status__in=ACTIVE_TRANSFER_STATUSES)
    elif scope == "history":
        transfers = transfers.filter(status__in=(
            TransferRequest.STATUS_COMPLETED,
            TransferRequest.STATUS_REJECTED,
            TransferRequest.STATUS_CANCELLED,
        ))
    target_classes = list(
        AcademicClass.objects.filter(
            branch=branch, is_active=True, is_archived=False
        ).select_related("programme", "branch", "academic_year").order_by(
            "level", "programme__title"
        )
    ) if branch else []
    return {
        "transfer_enrollments": enrollments,
        "transfer_rows": transfers.order_by("-created_at", "-id"),
        "transfer_target_classes": target_classes,
        "transfer_type_choices": TransferRequest.TYPE_CHOICES,
        "transfer_metrics": {
            "total": all_transfers.count(),
            "pending": all_transfers.filter(status__in=ACTIVE_TRANSFER_STATUSES).count(),
            "internal": all_transfers.filter(transfer_type=TransferRequest.TYPE_INTERNAL).count(),
            "outgoing": all_transfers.filter(transfer_type=TransferRequest.TYPE_OUTGOING).count(),
            "incoming": all_transfers.filter(transfer_type=TransferRequest.TYPE_INCOMING).count(),
            "completed": all_transfers.filter(status=TransferRequest.STATUS_COMPLETED).count(),
        },
        "transfer_q": query,
        "transfer_type_filter": transfer_type,
    }


def _get_or_create_school(*, branch, name, city="", user):
    normalized_name = (name or "").strip()
    if not normalized_name:
        raise ValidationError("Le nom de l'établissement est obligatoire.")
    school, _ = TransferSchool.objects.get_or_create(
        branch=branch,
        name=normalized_name,
        city=(city or "").strip(),
        defaults={"created_by": user},
    )
    return school


@transaction.atomic
def create_transfer_request(
    *, user, enrollment_id=None, transfer_type, target_class_id=None,
    target_school_name="", reason="", attachment=None, transfer_data=None,
):
    branch = get_user_branch(user)
    if branch is None:
        raise ValidationError("Aucune annexe n'est rattachée à ce compte directeur.")
    if transfer_type not in dict(TransferRequest.TYPE_CHOICES):
        raise ValidationError("Type de transfert invalide.")
    transfer_data = transfer_data or {}

    enrollment = None
    if transfer_type != TransferRequest.TYPE_INCOMING:
        enrollment = AcademicEnrollment.objects.select_related(
            "academic_class", "programme", "academic_year", "inscription", "student"
        ).filter(id=enrollment_id, branch=branch, is_active=True, is_archived=False).first()
        if enrollment is None:
            raise ValidationError("Étudiant introuvable pour cette annexe.")
        if TransferRequest.objects.filter(
            branch=branch, enrollment=enrollment, status__in=ACTIVE_TRANSFER_STATUSES
        ).exists():
            raise ValidationError("Un transfert est déjà actif pour cet étudiant.")

    target_class = None
    if target_class_id:
        target_class = AcademicClass.objects.select_related("programme", "academic_year").filter(
            id=target_class_id, branch=branch, is_active=True, is_archived=False
        ).first()
        if target_class is None:
            raise ValidationError("Classe de destination introuvable dans cette annexe.")

    if transfer_type == TransferRequest.TYPE_INTERNAL:
        if target_class is None:
            raise ValidationError("La classe de destination est obligatoire.")
        if target_class.pk == enrollment.academic_class_id:
            raise ValidationError("La classe de destination doit être différente.")
        if target_class.academic_year_id != enrollment.academic_year_id:
            raise ValidationError("Le transfert interne doit rester dans la même année académique.")
        if target_class.level.strip().upper() != enrollment.academic_class.level.strip().upper():
            raise ValidationError(
                "Un transfert interne ne peut pas changer le niveau acquis. Utilisez le passage d'année."
            )
        target_school_name = ""
    elif transfer_type == TransferRequest.TYPE_OUTGOING:
        if not (target_school_name or "").strip():
            raise ValidationError("L'école de destination est obligatoire.")
        target_class = None
    else:
        if target_class is None:
            raise ValidationError("La classe demandée est obligatoire pour étudier l'équivalence.")

    transfer = TransferRequest.objects.create(
        branch=branch,
        enrollment=enrollment,
        transfer_type=transfer_type,
        source_class=enrollment.academic_class if enrollment else None,
        target_class=target_class,
        target_school_name=(target_school_name or transfer_data.get("origin_school_name") or "").strip(),
        reason=(reason or "").strip(),
        attachment=attachment,
        status=TransferRequest.STATUS_SUBMITTED,
        created_by=user,
        submitted_at=timezone.now(),
        source_snapshot=_source_snapshot(enrollment),
    )

    if transfer_type == TransferRequest.TYPE_INTERNAL:
        InternalTransfer.objects.create(
            transfer_request=transfer,
            target_programme=target_class.programme,
            target_class=target_class,
            source_level=enrollment.academic_class.level,
            target_level=target_class.level,
            academic_decision_reference=(transfer_data.get("academic_decision_reference") or "").strip(),
        )
    elif transfer_type == TransferRequest.TYPE_OUTGOING:
        school = _get_or_create_school(
            branch=branch,
            name=target_school_name,
            city=transfer_data.get("school_city"),
            user=user,
        )
        OutgoingTransfer.objects.create(
            transfer_request=transfer,
            destination_school=school,
            destination_programme=(transfer_data.get("destination_programme") or "").strip(),
            destination_level=(transfer_data.get("destination_level") or "").strip(),
            academic_check_completed=bool(transfer_data.get("academic_check_completed")),
            administrative_check_completed=bool(transfer_data.get("administrative_check_completed")),
            financial_check_completed=bool(transfer_data.get("financial_check_completed")),
        )
    else:
        school = _get_or_create_school(
            branch=branch,
            name=transfer_data.get("origin_school_name"),
            city=transfer_data.get("school_city"),
            user=user,
        )
        IncomingTransfer.objects.create(
            transfer_request=transfer,
            origin_school=school,
            first_name=(transfer_data.get("first_name") or "").strip(),
            last_name=(transfer_data.get("last_name") or "").strip(),
            birth_date=transfer_data.get("birth_date"),
            birth_place=(transfer_data.get("birth_place") or "").strip(),
            gender=transfer_data.get("gender"),
            phone=(transfer_data.get("phone") or "").strip(),
            email=(transfer_data.get("email") or "").strip(),
            address=(transfer_data.get("address") or "").strip(),
            city=(transfer_data.get("city") or "").strip(),
            country=(transfer_data.get("country") or "Mali").strip(),
            requested_programme=target_class.programme,
            requested_class=target_class,
            requested_level=target_class.level,
            equivalence_notes=(transfer_data.get("equivalence_notes") or "").strip(),
        )

    if transfer.attachment:
        TransferDocument.objects.create(
            transfer_request=transfer,
            document_type=transfer_data.get("document_type") or TransferDocument.TYPE_REQUEST,
            title=(transfer_data.get("document_title") or "Pièce initiale du dossier").strip(),
            file=transfer.attachment.name,
            uploaded_by=user,
        )
    _log(
        transfer,
        actor=user,
        action="created",
        to_status=transfer.status,
        note=reason,
        snapshot=transfer.source_snapshot,
    )
    return transfer


def _record_decision(transfer, *, user, outcome, note=""):
    TransferDecision.objects.update_or_create(
        transfer_request=transfer,
        defaults={"outcome": outcome, "note": note, "decided_by": user, "decided_at": timezone.now()},
    )


def get_transfer_request_for_director(*, user, transfer_id):
    branch = get_user_branch(user)
    if branch is None:
        raise ValidationError("Aucune annexe n'est rattachée à ce compte directeur.")
    transfer = TransferRequest.objects.select_related(
        "enrollment", "enrollment__student", "source_class", "target_class",
        "internal_details", "outgoing_details", "outgoing_details__destination_school",
        "incoming_details", "incoming_details__origin_school", "incoming_details__requested_class",
        "incoming_details__candidature", "decision", "reviewed_by", "created_by",
    ).prefetch_related("documents__uploaded_by", "documents__verified_by", "history__actor").filter(
        pk=transfer_id, branch=branch
    ).first()
    if transfer is None:
        raise ValidationError("Dossier de transfert introuvable.")
    return transfer


def add_transfer_document(*, user, transfer_id, document_type, title, file):
    transfer = get_transfer_request_for_director(user=user, transfer_id=transfer_id)
    if document_type not in dict(TransferDocument.TYPE_CHOICES):
        raise ValidationError("Type de pièce invalide.")
    document = TransferDocument.objects.create(
        transfer_request=transfer,
        document_type=document_type,
        title=(title or file.name).strip(),
        file=file,
        uploaded_by=user,
    )
    _log(
        transfer,
        actor=user,
        action="document_uploaded",
        from_status=transfer.status,
        to_status=transfer.status,
        note=document.title,
        snapshot={"document_id": document.pk, "document_type": document.document_type},
    )
    return document


def review_transfer_document(*, user, document_id, action):
    branch = get_user_branch(user)
    document = TransferDocument.objects.select_related("transfer_request").filter(
        pk=document_id, transfer_request__branch=branch
    ).first()
    if document is None:
        raise ValidationError("Pièce de transfert introuvable.")
    normalized = (action or "").strip().lower()
    if normalized == "verify":
        document.status = TransferDocument.STATUS_VERIFIED
        action_label = "document_verified"
    elif normalized == "reject":
        document.status = TransferDocument.STATUS_REJECTED
        action_label = "document_rejected"
    else:
        raise ValidationError("Action documentaire inconnue.")
    document.verified_by = user
    document.verified_at = timezone.now()
    document.save(update_fields=["status", "verified_by", "verified_at"])
    _log(
        document.transfer_request,
        actor=user,
        action=action_label,
        from_status=document.transfer_request.status,
        to_status=document.transfer_request.status,
        note=document.title,
        snapshot={"document_id": document.pk, "document_status": document.status},
    )
    return document


def _apply_internal_transfer(transfer, *, user):
    enrollment = AcademicEnrollment.objects.select_for_update().select_related(
        "inscription__candidature", "academic_class"
    ).get(pk=transfer.enrollment_id, branch=transfer.branch)
    details = transfer.internal_details
    target = details.target_class
    if enrollment.academic_class_id != transfer.source_class_id:
        raise ValidationError("La classe actuelle ne correspond plus au dossier d'origine.")
    if target.branch_id != transfer.branch_id or target.academic_year_id != enrollment.academic_year_id:
        raise ValidationError("La classe cible n'appartient plus au périmètre autorisé.")
    if target.level.strip().upper() != enrollment.academic_class.level.strip().upper():
        raise ValidationError("Le niveau ne peut pas être modifié par un transfert interne.")

    inscription = enrollment.inscription
    candidature = inscription.candidature
    Candidature.objects.filter(pk=candidature.pk).update(programme=target.programme)
    type(inscription).objects.filter(pk=inscription.pk).update(
        academic_class=target,
        academic_level=target.level,
        updated_at=timezone.now(),
    )
    AcademicEnrollment.objects.filter(pk=enrollment.pk).update(
        academic_class=target,
        programme=target.programme,
        status=AcademicEnrollment.STATUS_ACTIVE,
        is_active=True,
        is_archived=False,
        archived_at=None,
    )
    details.applied_at = timezone.now()
    details.save(update_fields=["applied_at"])
    _log(
        transfer,
        actor=user,
        action="academic_placement_created",
        from_status=transfer.status,
        to_status=transfer.status,
        snapshot={
            "source": transfer.source_snapshot,
            "target_class_id": target.pk,
            "target_class": target.display_name,
            "target_programme_id": target.programme_id,
            "target_programme": str(target.programme),
            "level": target.level,
        },
    )


def _archive_outgoing_enrollment(transfer):
    enrollment = AcademicEnrollment.objects.select_for_update().select_related(
        "inscription", "student__student_profile"
    ).get(pk=transfer.enrollment_id, branch=transfer.branch)
    now = timezone.now()
    enrollment.status = AcademicEnrollment.STATUS_TRANSFERRED
    enrollment.is_active = False
    enrollment.is_archived = True
    enrollment.archived_at = now
    enrollment.save(update_fields=["status", "is_active", "is_archived", "archived_at"])
    inscription = enrollment.inscription
    inscription.status = inscription.STATUS_COMPLETED
    inscription.is_archived = True
    inscription.archived_at = now
    inscription.save(update_fields=["status", "is_archived", "archived_at", "updated_at"])
    student_profile = getattr(enrollment.student, "student_profile", None)
    if student_profile is not None:
        student_profile.current_academic_enrollment = None
        student_profile.is_active = False
        student_profile.save(update_fields=["current_academic_enrollment", "is_active"])
    details = transfer.outgoing_details
    details.handover_at = now
    details.save(update_fields=["handover_at"])


def _incoming_entry_year(level):
    match = re.search(r"(\d+)", level or "")
    return max(int(match.group(1)), 1) if match else 1


def _create_incoming_candidature(transfer, *, user):
    details = transfer.incoming_details
    academic_class = details.requested_class
    if academic_class is None or academic_class.branch_id != transfer.branch_id:
        raise ValidationError("La classe demandée n'est plus disponible dans cette annexe.")
    duplicate = Candidature.objects.filter(
        email__iexact=details.email,
        programme=details.requested_programme,
        branch=transfer.branch,
        academic_year=academic_class.academic_year.name,
        is_deleted=False,
    ).first()
    if duplicate is not None and details.candidature_id != duplicate.pk:
        raise ValidationError("Une candidature existe déjà pour cette personne et ce programme.")
    candidature = details.candidature or Candidature.objects.create(
        programme=details.requested_programme,
        branch=transfer.branch,
        academic_year=academic_class.academic_year.name,
        entry_year=_incoming_entry_year(details.requested_level),
        first_name=details.first_name,
        last_name=details.last_name,
        birth_date=details.birth_date,
        birth_place=details.birth_place,
        gender=details.gender,
        phone=details.phone,
        email=details.email,
        address=details.address,
        city=details.city,
        country=details.country,
        status="submitted",
        admin_comment=(
            f"Candidature créée depuis le transfert entrant {transfer.reference}. "
            "L'admission et l'inscription suivent le circuit normal."
        ),
    )
    details.candidature = candidature
    details.save(update_fields=["candidature"])
    return candidature


@transaction.atomic
def review_transfer_request(*, user, transfer_id, action, decision_note="", checks=None):
    branch = get_user_branch(user)
    if branch is None:
        raise ValidationError("Aucune annexe n'est rattachée à ce compte directeur.")
    transfer = TransferRequest.objects.select_for_update().select_related(
        "branch", "enrollment", "source_class", "target_class", "internal_details",
        "outgoing_details", "incoming_details", "incoming_details__requested_class",
        "incoming_details__requested_programme",
    ).filter(id=transfer_id, branch=branch).first()
    if transfer is None:
        raise ValidationError("Demande de transfert introuvable.")
    normalized = (action or "").strip().lower()
    note = (decision_note or "").strip()

    if normalized == "start_review":
        if transfer.status not in (TransferRequest.STATUS_SUBMITTED, TransferRequest.STATUS_AWAITING_DOCUMENTS):
            raise ValidationError("Ce dossier ne peut pas être placé en étude.")
        _set_status(transfer, actor=user, status=TransferRequest.STATUS_UNDER_REVIEW, action="review_started", note=note)
    elif normalized == "request_documents":
        if transfer.status not in (TransferRequest.STATUS_SUBMITTED, TransferRequest.STATUS_UNDER_REVIEW):
            raise ValidationError("Ce dossier ne peut plus être renvoyé pour pièces.")
        _set_status(transfer, actor=user, status=TransferRequest.STATUS_AWAITING_DOCUMENTS, action="documents_requested", note=note)
    elif normalized in {"reject", "rejected"}:
        if transfer.status not in ACTIVE_TRANSFER_STATUSES:
            raise ValidationError("Ce dossier a déjà reçu une décision définitive.")
        _record_decision(transfer, user=user, outcome=TransferDecision.OUTCOME_REJECTED, note=note)
        _set_status(transfer, actor=user, status=TransferRequest.STATUS_REJECTED, action="rejected", note=note)
    elif normalized in {"validate", "approve"}:
        if transfer.status not in (
            TransferRequest.STATUS_SUBMITTED,
            TransferRequest.STATUS_UNDER_REVIEW,
            TransferRequest.STATUS_AWAITING_DOCUMENTS,
        ):
            raise ValidationError("Ce dossier ne peut pas être approuvé dans son état actuel.")
        if transfer.transfer_type == TransferRequest.TYPE_INTERNAL:
            _apply_internal_transfer(transfer, user=user)
            _record_decision(transfer, user=user, outcome=TransferDecision.OUTCOME_APPROVED, note=note)
            _set_status(transfer, actor=user, status=TransferRequest.STATUS_COMPLETED, action="internal_transfer_completed", note=note)
        elif transfer.transfer_type == TransferRequest.TYPE_OUTGOING:
            details = transfer.outgoing_details
            checks = checks or {}
            for field in (
                "academic_check_completed", "administrative_check_completed", "financial_check_completed"
            ):
                if field in checks:
                    setattr(details, field, bool(checks[field]))
            details.save(update_fields=[
                "academic_check_completed", "administrative_check_completed", "financial_check_completed"
            ])
            if not details.checks_completed:
                raise ValidationError("Les contrôles académique, administratif et financier doivent être terminés.")
            _record_decision(transfer, user=user, outcome=TransferDecision.OUTCOME_APPROVED, note=note)
            _set_status(transfer, actor=user, status=TransferRequest.STATUS_APPROVED, action="outgoing_transfer_approved", note=note)
        else:
            candidature = _create_incoming_candidature(transfer, user=user)
            _record_decision(transfer, user=user, outcome=TransferDecision.OUTCOME_APPROVED, note=note)
            _set_status(
                transfer,
                actor=user,
                status=TransferRequest.STATUS_COMPLETED,
                action="incoming_transfer_admitted_to_application",
                note=f"{note} Candidature #{candidature.pk}".strip(),
            )
    elif normalized == "handover":
        if transfer.transfer_type != TransferRequest.TYPE_OUTGOING or transfer.status != TransferRequest.STATUS_APPROVED:
            raise ValidationError("Seul un départ approuvé peut être remis à l'établissement destinataire.")
        _archive_outgoing_enrollment(transfer)
        _set_status(transfer, actor=user, status=TransferRequest.STATUS_COMPLETED, action="outgoing_handover_completed", note=note)
    else:
        raise ValidationError("Action de transfert inconnue.")
    return transfer
