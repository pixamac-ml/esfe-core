from django.core.exceptions import ValidationError

from academics.models import AcademicClass, AcademicEnrollment
from accounts.dashboards.helpers import get_user_branch
from portal.models import TransferRequest


def build_director_transfer_context(*, branch):
    enrollments = list(
        AcademicEnrollment.objects.select_related(
            "academic_class",
            "student",
            "student__student_profile",
            "student__student_profile__inscription__candidature",
        )
        .filter(branch=branch, is_active=True)
        .order_by(
            "academic_class__level",
            "student__student_profile__inscription__candidature__last_name",
            "student__student_profile__inscription__candidature__first_name",
            "student__username",
        )[:200]
    ) if branch else []
    transfers = list(
        TransferRequest.objects.select_related(
            "enrollment",
            "enrollment__student",
            "enrollment__student__student_profile",
            "source_class",
            "target_class",
        )
        .filter(branch=branch)
        .order_by("-created_at", "-id")[:30]
    ) if branch else []
    target_classes = list(
        AcademicClass.objects.filter(branch=branch, is_active=True).select_related("programme", "branch").order_by("level", "programme__title")
    ) if branch else []
    return {
        "transfer_enrollments": enrollments,
        "transfer_rows": transfers,
        "transfer_target_classes": target_classes,
        "transfer_type_choices": TransferRequest.TYPE_CHOICES,
    }


def create_transfer_request(*, user, enrollment_id, transfer_type, target_class_id=None, target_school_name="", reason="", attachment=None):
    branch = get_user_branch(user)
    if branch is None:
        raise ValidationError("Aucune annexe n'est rattachee a ce compte directeur.")

    enrollment = AcademicEnrollment.objects.select_related("academic_class").filter(
        id=enrollment_id,
        branch=branch,
        is_active=True,
    ).first()
    if enrollment is None:
        raise ValidationError("Etudiant introuvable pour cette annexe.")

    if transfer_type not in dict(TransferRequest.TYPE_CHOICES):
        raise ValidationError("Type de transfert invalide.")

    target_class = None
    if transfer_type == TransferRequest.TYPE_CLASS:
        if not target_class_id:
            raise ValidationError("La classe de destination est obligatoire.")
        target_class = AcademicClass.objects.filter(id=target_class_id, branch=branch, is_active=True).first()
        if target_class is None:
            raise ValidationError("Classe de destination introuvable.")
        if target_class.id == enrollment.academic_class_id:
            raise ValidationError("La classe de destination doit etre differente.")
        target_school_name = ""
    else:
        if not (target_school_name or "").strip():
            raise ValidationError("L'ecole de destination est obligatoire.")
        target_class = None

    return TransferRequest.objects.create(
        branch=branch,
        enrollment=enrollment,
        transfer_type=transfer_type,
        source_class=enrollment.academic_class,
        target_class=target_class,
        target_school_name=(target_school_name or "").strip(),
        reason=(reason or "").strip(),
        attachment=attachment,
        status=TransferRequest.STATUS_SUBMITTED,
        created_by=user,
    )


def review_transfer_request(*, user, transfer_id, action):
    branch = get_user_branch(user)
    if branch is None:
        raise ValidationError("Aucune annexe n'est rattachee a ce compte directeur.")

    transfer = TransferRequest.objects.select_related("branch").filter(
        id=transfer_id,
        branch=branch,
    ).first()
    if transfer is None:
        raise ValidationError("Demande de transfert introuvable.")

    normalized = (action or "").strip().lower()
    if normalized == "validate":
        transfer.status = TransferRequest.STATUS_VALIDATED
    elif normalized == "reject":
        transfer.status = TransferRequest.STATUS_REJECTED
    else:
        raise ValidationError("Action de transfert inconnue.")

    transfer.reviewed_by = user
    transfer.save(update_fields=["status", "reviewed_by", "updated_at"])
    return transfer
