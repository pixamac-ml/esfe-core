# students/services/create_student_after_first_payment.py

import secrets

from django.contrib.auth import get_user_model
from django.db import transaction
from django.core.exceptions import ValidationError

from students.models import Student
from inscriptions.models import Inscription

User = get_user_model()


def generate_student_username(inscription):
    """
    Génère un username unique pour l'étudiant.
    """
    return f"etu_esfe_{inscription.id}"


def generate_student_matricule(inscription):
    """
    Génère le matricule académique.
    Format : ESFE-00001
    """
    return f"ESFE-{inscription.id:05d}"


def create_student_after_first_payment(inscription):
    """
    Création robuste et idempotente du compte étudiant.

    Conditions :
    - inscription active
    - paiement validé existant
    - un seul student par inscription
    """

    if not inscription:
        raise ValidationError("Inscription requise.")

    # ==========================================================
    # VERIFICATION STATUT
    # ==========================================================

    if inscription.status not in ["active", "partial_paid"]:
        # Pas encore éligible
        return None

    candidature = inscription.candidature

    username = generate_student_username(inscription)

    with transaction.atomic():

        # verrou inscription (évite création concurrente)
        inscription_locked = (
            Inscription.objects
            .select_for_update()
            .get(pk=inscription.pk)
        )

        # ==========================================================
        # STUDENT EXISTANT
        # ==========================================================

        existing_student = Student.objects.filter(
            inscription=inscription_locked
        ).select_related("user").first()

        if existing_student:
            return {
                "student": existing_student,
                "password": None
            }

        # ==========================================================
        # USER
        # ==========================================================

        user = User.objects.filter(username=username).first()

        raw_password = None

        if not user:

            raw_password = secrets.token_urlsafe(8)

            email = candidature.email or f"etu_{inscription.id}@esfe.local"

            user = User.objects.create_user(
                username=username,
                email=email,
                password=raw_password,
                first_name=candidature.first_name,
                last_name=candidature.last_name,
            )

        # ==========================================================
        # CREATION STUDENT
        # ==========================================================

        student = Student.objects.create(
            user=user,
            inscription=inscription_locked,
            matricule=generate_student_matricule(inscription_locked)
        )

    return {
        "student": student,
        "password": raw_password
    }