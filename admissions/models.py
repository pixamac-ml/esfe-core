from django.db import models
from django.utils import timezone

from formations.models import Programme, RequiredDocument


class Candidature(models.Model):

    # ----------------------------------
    # LIEN ACADÉMIQUE
    # ----------------------------------
    programme = models.ForeignKey(
        Programme,
        on_delete=models.PROTECT,
        related_name="candidatures"
    )

    # ----------------------------------
    # ANNÉE D’ENTRÉE (CLÉ MÉTIER)
    # ----------------------------------
    entry_year = models.PositiveSmallIntegerField(
        default=1,
        help_text="Année d’entrée dans le programme (1 = première année)"
    )

    # ----------------------------------
    # INFORMATIONS PERSONNELLES
    # ----------------------------------
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)

    birth_date = models.DateField()
    birth_place = models.CharField(max_length=150)

    gender = models.CharField(
        max_length=10,
        choices=[
            ("male", "Masculin"),
            ("female", "Féminin"),
        ]
    )

    # ----------------------------------
    # CONTACT
    # ----------------------------------
    phone = models.CharField(max_length=30)
    email = models.EmailField()

    address = models.CharField(
        max_length=255,
        blank=True
    )

    city = models.CharField(
        max_length=100,
        blank=True
    )

    country = models.CharField(
        max_length=100,
        default="Mali"
    )

    # ----------------------------------
    # STATUT MÉTIER
    # ----------------------------------
    STATUS_CHOICES = (
        ("submitted", "Soumise"),
        ("under_review", "En cours d’analyse"),
        ("to_complete", "À compléter"),
        ("accepted", "Acceptée"),
        ("accepted_with_reserve", "Acceptée sous réserve"),
        ("rejected", "Refusée"),
    )

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="submitted"
    )

    admin_comment = models.TextField(
        blank=True,
        help_text="Commentaire interne (non visible par le candidat)"
    )

    # ----------------------------------
    # MÉTADONNÉES
    # ----------------------------------
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-submitted_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["programme"]),
        ]

    def __str__(self):
        return f"{self.last_name} {self.first_name} – {self.programme.title}"

    # ----------------------------------
    # MÉTHODES MÉTIER
    # ----------------------------------
    def mark_reviewed(self):
        self.reviewed_at = timezone.now()
        self.save(update_fields=["reviewed_at"])


class CandidatureDocument(models.Model):

    candidature = models.ForeignKey(
        Candidature,
        on_delete=models.CASCADE,
        related_name="documents"
    )

    document_type = models.ForeignKey(
        RequiredDocument,
        on_delete=models.PROTECT
    )

    file = models.FileField(
        upload_to="candidatures/documents/"
    )

    is_valid = models.BooleanField(
        default=False,
        help_text="Validé par l’administration"
    )

    admin_note = models.CharField(
        max_length=255,
        blank=True
    )

    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("candidature", "document_type")
        ordering = ["uploaded_at"]

    def __str__(self):
        return f"{self.document_type.name} – {self.candidature}"
