# students/models.py

from django.db import models
from django.contrib.auth import get_user_model

from inscriptions.models import Inscription

User = get_user_model()


class Student(models.Model):
    """
    Étudiant officiel de l’établissement.
    Créé automatiquement après le premier paiement validé.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="student_profile"
    )

    inscription = models.OneToOneField(
        Inscription,
        on_delete=models.PROTECT,
        related_name="student"
    )

    matricule = models.CharField(
        max_length=30,
        unique=True
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Étudiant actif dans l’établissement"
    )

    created_at = models.DateTimeField(auto_now_add=True)
