import secrets
import logging

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

from academics.services.enrollment_service import assign_student_academic_enrollment
from accounts.models import Profile
from inscriptions.models import Inscription
from students.models import Student

User = get_user_model()
logger = logging.getLogger(__name__)


def _safe_assign_academic_enrollment(inscription):
    try:
        return assign_student_academic_enrollment(inscription)
    except Exception:
        logger.exception(
            "Echec non bloquant de liaison academique pour inscription=%s",
            getattr(inscription, "pk", None),
        )
        return {
            "status": "error",
            "enrollment": None,
            "reason": "unexpected_error",
        }


def ensure_student_role(user):
    profile, _ = Profile.objects.get_or_create(user=user)
    changed_fields = []

    if profile.role != "student":
        profile.role = "student"
        changed_fields.append("role")

    if changed_fields:
        profile.save(update_fields=changed_fields + ["updated_at"])

    return profile


def create_student_after_first_payment(inscription):
    """
    Creation automatique de l'etudiant apres validation du premier paiement.

    Regles metier :
    - la candidature doit etre acceptee (ou acceptee sous reserve)
    - au moins un paiement valide doit exister pour l'inscription
    - l'inscription partiellement payee reste eligible
    - la fonction est idempotente
    """

    if not inscription:
        return None

    with transaction.atomic():
        from payments.models import Payment

        inscription_locked = (
            Inscription.objects
            .select_for_update()
            .select_related("candidature")
            .get(pk=inscription.pk)
        )
        candidature = inscription_locked.candidature

        if candidature.status not in {"accepted", "accepted_with_reserve"}:
            return None

        has_validated_payment = Payment.objects.filter(
            inscription=inscription_locked,
            status=Payment.STATUS_VALIDATED,
        ).exists()
        if not has_validated_payment:
            return None

        existing_student = (
            Student.objects
            .filter(inscription=inscription_locked)
            .select_related("user")
            .first()
        )
        if existing_student:
            ensure_student_role(existing_student.user)
            academic_result = _safe_assign_academic_enrollment(inscription_locked)
            return {
                "student": existing_student,
                "password": None,
                "created": False,
                "academic_enrollment": academic_result,
            }

        username = f"etu_esfe{inscription_locked.id}"
        user = User.objects.filter(username=username).first()
        raw_password = None

        if not user:
            raw_password = secrets.token_urlsafe(10)
            user = User.objects.create_user(
                username=username,
                email=candidature.email,
                password=raw_password,
                first_name=candidature.first_name,
                last_name=candidature.last_name,
            )

        conflicting_student = Student.objects.filter(user=user).select_related("inscription").first()
        if conflicting_student:
            if conflicting_student.inscription_id != inscription_locked.id:
                raise ValidationError(
                    "Un compte etudiant existe deja pour cet utilisateur sur une autre inscription."
                )
            ensure_student_role(user)
            academic_result = _safe_assign_academic_enrollment(inscription_locked)
            return {
                "student": conflicting_student,
                "password": None,
                "created": False,
                "academic_enrollment": academic_result,
            }

        ensure_student_role(user)

        matricule = f"ESFE-{inscription_locked.id:05d}"
        if Student.objects.filter(matricule=matricule).exists():
            matricule = f"ESFE-{inscription_locked.id:05d}-{secrets.token_hex(2)}"

        student = Student.objects.create(
            user=user,
            inscription=inscription_locked,
            matricule=matricule,
        )

        academic_result = _safe_assign_academic_enrollment(inscription_locked)

        return {
            "student": student,
            "password": raw_password,
            "created": True,
            "academic_enrollment": academic_result,
        }
