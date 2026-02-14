from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator

from formations.models import Programme, RequiredDocument


class Candidature(models.Model):

    # ==================================================
    # LIEN ACADÉMIQUE
    # ==================================================
    programme = models.ForeignKey(
        Programme,
        on_delete=models.PROTECT,
        related_name="candidatures"
    )

    # Année académique réelle (ex: 2025-2026)
    academic_year = models.CharField(
        max_length=9,
        help_text="Année académique (ex: 2025-2026)"
    )

    # Année d’entrée dans le programme (1 = L1, 2 = L2…)
    entry_year = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Année d’entrée dans le programme"
    )

    # ==================================================
    # INFORMATIONS PERSONNELLES
    # ==================================================
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)

    birth_date = models.DateField()
    birth_place = models.CharField(max_length=150)

    GENDER_CHOICES = (
        ("male", "Masculin"),
        ("female", "Féminin"),
    )

    gender = models.CharField(
        max_length=10,
        choices=GENDER_CHOICES
    )

    # ==================================================
    # CONTACT
    # ==================================================
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

    # ==================================================
    # STATUT MÉTIER
    # ==================================================
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
        default="submitted",
        db_index=True
    )

    admin_comment = models.TextField(
        blank=True,
        help_text="Commentaire interne (non visible par le candidat)"
    )

    # ==================================================
    # MÉTADONNÉES
    # ==================================================
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True
    )
    updated_at = models.DateTimeField(auto_now=True)

    # ==================================================
    # META
    # ==================================================
    class Meta:
        ordering = ["-submitted_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["email", "programme", "academic_year"],
                name="unique_candidature_per_year"
            )
        ]

        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["programme"]),
            models.Index(fields=["programme", "entry_year", "status"]),
            models.Index(fields=["academic_year"]),
        ]

    # ==================================================
    # REPRÉSENTATION
    # ==================================================
    def __str__(self):
        return f"{self.full_name} – {self.programme.title} ({self.academic_year})"

    @property
    def full_name(self):
        return f"{self.last_name} {self.first_name}"

    # ==================================================
    # MÉTHODES MÉTIER
    # ==================================================
    def mark_reviewed(self):
        self.reviewed_at = timezone.now()
        self.save(update_fields=["reviewed_at"])

    @property
    def is_reviewed(self):
        return self.reviewed_at is not None

    @property
    def documents_count(self):
        return self.documents.count()

    @property
    def validated_documents_count(self):
        return self.documents.filter(is_valid=True).count()

    @property
    def all_documents_valid(self):
        required_count = RequiredDocument.objects.count()
        return self.validated_documents_count >= required_count


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
        constraints = [
            models.UniqueConstraint(
                fields=["candidature", "document_type"],
                name="unique_document_per_type"
            )
        ]
        ordering = ["uploaded_at"]

        indexes = [
            models.Index(fields=["is_valid"]),
            models.Index(fields=["document_type"]),
        ]

    def __str__(self):
        return f"{self.document_type.name} – {self.candidature.full_name}"
