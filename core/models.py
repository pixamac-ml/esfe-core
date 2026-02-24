from django.db import models
from django.core.exceptions import ValidationError
from ckeditor.fields import RichTextField


# ==========================================================
# INSTITUTION (UNE SEULE INSTANCE)
# ==========================================================

class Institution(models.Model):
    name = models.CharField(max_length=255)
    short_name = models.CharField(max_length=100, blank=True)

    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default="Mali")

    phone = models.CharField(max_length=50)
    email = models.EmailField()

    legal_status = models.CharField(
        max_length=255,
        blank=True,
        help_text="Statut juridique officiel"
    )

    approval_number = models.CharField(
        max_length=255,
        blank=True,
        help_text="Numéro d’agrément ou autorisation"
    )

    director_title = models.CharField(
        max_length=255,
        default="Direction Générale"
    )

    hosting_provider = models.CharField(max_length=255, blank=True)
    hosting_location = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if Institution.objects.exclude(pk=self.pk).exists():
            raise ValidationError("Une seule institution est autorisée.")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Institution"
        verbose_name_plural = "Institution"


# ==========================================================
# LEGAL PAGE HISTORY (VERSIONNAGE)
# ==========================================================

class LegalPageHistory(models.Model):
    page = models.ForeignKey("LegalPage", on_delete=models.CASCADE)
    version = models.CharField(max_length=20)
    content_snapshot = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.page.title} - v{self.version}"

    class Meta:
        verbose_name = "Historique de page"
        verbose_name_plural = "Historique des pages"


# ==========================================================
# LEGAL PAGE
# ==========================================================

class LegalPage(models.Model):

    PAGE_TYPES = (
        ("legal", "Mentions légales"),
        ("privacy", "Politique de confidentialité"),
        ("terms", "Conditions d’utilisation"),
    )

    STATUS_CHOICES = (
        ("draft", "Brouillon"),
        ("review", "En révision"),
        ("published", "Publié"),
    )

    page_type = models.CharField(
        max_length=20,
        choices=PAGE_TYPES,
        unique=True
    )

    title = models.CharField(max_length=255)
    introduction = RichTextField(blank=True)

    version = models.CharField(max_length=20, default="1.0")

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="draft"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["page_type"]

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)

        # Historique seulement si nouvelle version ou nouvelle page
        if is_new or not LegalPageHistory.objects.filter(
            page=self,
            version=self.version
        ).exists():

            LegalPageHistory.objects.create(
                page=self,
                version=self.version,
                content_snapshot=self.introduction or ""
            )

    def __str__(self):
        return f"{self.title} (v{self.version})"

    class Meta:
        verbose_name = "Page légale"
        verbose_name_plural = "Pages légales"
        ordering = ["page_type"]


# ==========================================================
# LEGAL SECTIONS
# ==========================================================

class LegalSection(models.Model):
    page = models.ForeignKey(
        LegalPage,
        on_delete=models.CASCADE,
        related_name="sections"
    )

    title = models.CharField(max_length=255)
    content = RichTextField()

    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.page.title} - {self.title}"

    class Meta:
        verbose_name = "Section légale"
        verbose_name_plural = "Sections légales"
        ordering = ["order"]


# ==========================================================
# SIDEBAR BLOCKS
# ==========================================================

class LegalSidebarBlock(models.Model):
    page = models.ForeignKey(
        LegalPage,
        on_delete=models.CASCADE,
        related_name="sidebar_blocks"
    )

    title = models.CharField(max_length=255)
    content = RichTextField()
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.page.title} - Bloc : {self.title}"



class InstitutionStat(models.Model):
    label = models.CharField(max_length=100)
    value = models.PositiveIntegerField()
    suffix = models.CharField(max_length=5, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']






from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils.functional import cached_property
import uuid


class ContactMessage(models.Model):

    SUBJECT_CHOICES = [
        ("admission", "Admission"),
        ("formation", "Information formation"),
        ("inscription", "Inscription administrative"),
        ("payment", "Paiement"),
        ("partnership", "Partenariat"),
        ("complaint", "Réclamation"),
        ("other", "Autre"),
    ]

    STATUS_CHOICES = [
        ("new", "Nouveau"),
        ("in_progress", "En cours"),
        ("answered", "Répondu"),
        ("closed", "Clôturé"),
    ]

    PRIORITY_CHOICES = [
        ("low", "Faible"),
        ("normal", "Normale"),
        ("high", "Élevée"),
        ("urgent", "Urgente"),
    ]

    reference = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    full_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)

    subject = models.CharField(max_length=50, choices=SUBJECT_CHOICES)
    message = models.TextField()
    reply = models.TextField(blank=True, help_text="Réponse envoyée au contact")

    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default="normal"
    )

    sla_hours = models.PositiveIntegerField(
        default=48,
        help_text="Temps maximal de traitement en heures"
    )

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="new"
    )

    assigned_to = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    answered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["priority"]),
            models.Index(fields=["created_at"]),
        ]
        verbose_name = "Message de contact"
        verbose_name_plural = "Messages de contact"

    # ===============================
    # ASSIGNATION INTELLIGENTE
    # ===============================

    def auto_assign(self):
        if self.assigned_to:
            return

        subject_group_map = {
            "payment": "Gestionnaire",
            "admission": "Secretaire Academique",
            "inscription": "Secretaire Academique",
            "formation": "Secretaire Academique",
            "partnership": "Direction",
            "complaint": "Responsable Qualite",
            "other": "Support",
        }

        group_name = subject_group_map.get(self.subject)

        if not group_name:
            return

        try:
            group = Group.objects.get(name=group_name)
            user = group.user_set.filter(is_active=True).first()
            if user:
                self.assigned_to = user
        except Group.DoesNotExist:
            pass

    # ===============================
    # LOGIQUE MÉTIER
    # ===============================

    def save(self, *args, **kwargs):

        if self.subject == "payment":
            self.priority = "high"
        elif self.subject == "complaint":
            self.priority = "urgent"

        if self.priority == "urgent":
            self.sla_hours = 8
        elif self.priority == "high":
            self.sla_hours = 24
        elif self.priority == "normal":
            self.sla_hours = 48
        else:
            self.sla_hours = 72

        self.auto_assign()

        super().save(*args, **kwargs)

    # ===============================
    # INDICATEURS PERFORMANCE
    # ===============================

    @cached_property
    def deadline(self):
        return self.created_at + timezone.timedelta(hours=self.sla_hours)

    @property
    def is_overdue(self):
        if self.answered_at:
            return False
        return timezone.now() > self.deadline

    @property
    def remaining_hours(self):
        if self.answered_at:
            return 0
        delta = self.deadline - timezone.now()
        return round(delta.total_seconds() / 3600, 2)

    @property
    def response_time(self):
        if self.answered_at:
            delta = self.answered_at - self.created_at
            return round(delta.total_seconds() / 3600, 2)
        return None

    @property
    def sla_respected(self):
        if not self.answered_at:
            return None
        return self.response_time <= self.sla_hours

    def mark_as_answered(self):
        self.status = "answered"
        self.answered_at = timezone.now()
        self.save(update_fields=["status", "answered_at"])

    def close(self):
        self.status = "closed"
        self.save(update_fields=["status"])

    def __str__(self):
        return f"{self.full_name} - {self.get_subject_display()}"



class AboutSection(models.Model):
    title = models.CharField(max_length=255)
    content = RichTextField()
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order"]
        verbose_name = "Section À propos"
        verbose_name_plural = "Sections À propos"

    def __str__(self):
        return self.title