# students/models.py

from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from inscriptions.models import Inscription

User = get_user_model()


class Student(models.Model):
    """
    Étudiant officiel de l’établissement.

    Créé automatiquement après le premier paiement validé.
    L'étudiant est lié à une inscription unique.
    """

    # =====================================================
    # RELATIONS
    # =====================================================

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="student_profile",
        db_index=True
    )

    inscription = models.OneToOneField(
        Inscription,
        on_delete=models.PROTECT,
        related_name="student",
        db_index=True
    )

    # =====================================================
    # IDENTITÉ ACADÉMIQUE
    # =====================================================

    matricule = models.CharField(
        max_length=30,
        unique=True,
        db_index=True
    )

    # =====================================================
    # STATUT
    # =====================================================

    is_active = models.BooleanField(
        default=True,
        help_text="Étudiant actif dans l’établissement"
    )

    # =====================================================
    # MÉTADONNÉES
    # =====================================================

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:

        ordering = ["-created_at"]

        indexes = [
            models.Index(fields=["matricule"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["created_at"]),
        ]

    # =====================================================
    # VALIDATION MÉTIER
    # =====================================================

    def clean(self):

        if not self.inscription:
            raise ValidationError("Une inscription est requise.")

        if not self.user:
            raise ValidationError("Un utilisateur est requis.")

        if self.inscription.status not in {"partial_paid", "active"}:
            raise ValidationError(
                "Impossible de créer un étudiant si l'inscription n'a pas encore de paiement validé."
            )

    # =====================================================
    # REPRÉSENTATION
    # =====================================================

    def __str__(self):

        try:
            c = self.inscription.candidature
            return f"{c.last_name} {c.first_name} ({self.matricule})"
        except Exception:
            return f"Student {self.matricule}"

    # =====================================================
    # ACCÈS RAPIDE AUX DONNÉES
    # =====================================================

    @property
    def full_name(self):

        c = self.inscription.candidature
        return f"{c.first_name} {c.last_name}"

    @property
    def email(self):

        return self.inscription.candidature.email

    @property
    def programme(self):

        return self.inscription.candidature.programme

    # =====================================================
    # PROPRIÉTÉS ACADÉMIQUES
    # =====================================================

    @property
    def programme_title(self):

        return self.programme.title

    @property
    def is_enrolled(self):

        return self.is_active and self.inscription.status == "active"

    # =====================================================
    # UTILITAIRES
    # =====================================================

    def deactivate(self):

        self.is_active = False
        self.save(update_fields=["is_active"])

    def reactivate(self):

        self.is_active = True
        self.save(update_fields=["is_active"])