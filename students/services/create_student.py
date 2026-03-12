import secrets

from django.contrib.auth import get_user_model
from django.db import transaction
from django.core.exceptions import ValidationError

from students.models import Student

User = get_user_model()


def create_student_after_first_payment(inscription):
    """
    Création automatique de l'étudiant après validation du premier paiement.

    RÈGLES MÉTIER :

    - La candidature doit être ACCEPTÉE
    - L'inscription doit être ACTIVE
    - Un étudiant ne peut exister qu'une seule fois par inscription
    - La fonction est idempotente (appel multiple sans duplication)
    """

    candidature = inscription.candidature

    # ==================================================
    # VALIDATIONS MÉTIER
    # ==================================================

    if candidature.status != "accepted":
        raise ValidationError(
            "Impossible de créer un étudiant : candidature non acceptée."
        )

    if inscription.status != "active":
        # Sécurité supplémentaire
        return None

    # ==================================================
    # IDENTIFIANTS
    # ==================================================

    username = f"etu_esfe{inscription.id}"

    # ==================================================
    # TRANSACTION SÉCURISÉE
    # ==================================================

    with transaction.atomic():

        # Vérifier si l'étudiant existe déjà
        existing_student = Student.objects.filter(
            inscription=inscription
        ).select_related("user").first()

        if existing_student:
            return None

        # ==================================================
        # CRÉATION / RÉCUPÉRATION USER
        # ==================================================

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

        # ==================================================
        # MATRICULE ÉTUDIANT
        # ==================================================

        matricule = f"ESFE-{inscription.id:05d}"

        # Vérifier unicité du matricule
        if Student.objects.filter(matricule=matricule).exists():
            matricule = f"ESFE-{inscription.id:05d}-{secrets.token_hex(2)}"

        # ==================================================
        # CRÉATION STUDENT
        # ==================================================

        student = Student.objects.create(
            user=user,
            inscription=inscription,
            matricule=matricule
        )

    # ==================================================
    # RETOUR RÉSULTAT
    # ==================================================

    return {
        "student": student,
        "password": raw_password,
    }