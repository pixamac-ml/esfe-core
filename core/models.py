from django.db import models
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils.functional import cached_property
from django_ckeditor_5.fields import CKEditor5Field
import uuid


# ==========================================================
# INSTITUTION (SINGLETON)
# ==========================================================

class Institution(models.Model):
    name = models.CharField(max_length=255)
    short_name = models.CharField(max_length=100, blank=True)

    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default="Mali")

    phone = models.CharField(max_length=50)
    email = models.EmailField()

    is_active = models.BooleanField(default=True)

    legal_status = models.CharField(max_length=255, blank=True)
    approval_number = models.CharField(max_length=255, blank=True)
    director_title = models.CharField(max_length=255, default="Direction Générale")

    hosting_provider = models.CharField(max_length=255, blank=True)
    hosting_location = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if Institution.objects.exclude(pk=self.pk).exists():
            raise ValidationError("Une seule institution est autorisée.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Institution"
        verbose_name_plural = "Institution"


# ==========================================================
# INSTITUTION STATS
# ==========================================================

class InstitutionStat(models.Model):
    label = models.CharField(max_length=100)
    value = models.PositiveIntegerField()
    suffix = models.CharField(max_length=5, blank=True)

    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]
        verbose_name = "Statistique"
        verbose_name_plural = "Statistiques"

    def __str__(self):
        return self.label


# ==========================================================
# LEGAL PAGES
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

    page_type = models.CharField(max_length=20, choices=PAGE_TYPES, unique=True)
    title = models.CharField(max_length=255)
    introduction = CKEditor5Field("Introduction", config_name="default", blank=True)

    version = models.CharField(max_length=20, default="1.0")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)

        if is_new or not LegalPageHistory.objects.filter(
            page=self, version=self.version
        ).exists():
            LegalPageHistory.objects.create(
                page=self,
                version=self.version,
                content_snapshot=self.introduction or "",
            )

    def __str__(self):
        return f"{self.title} (v{self.version})"

    class Meta:
        ordering = ["page_type"]
        verbose_name = "Page légale"
        verbose_name_plural = "Pages légales"


class LegalPageHistory(models.Model):
    page = models.ForeignKey(LegalPage, on_delete=models.CASCADE)
    version = models.CharField(max_length=20)
    content_snapshot = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Historique de page"
        verbose_name_plural = "Historique des pages"

    def __str__(self):
        return f"{self.page.title} - v{self.version}"


class LegalSection(models.Model):
    page = models.ForeignKey(
        LegalPage,
        on_delete=models.CASCADE,
        related_name="sections"
    )

    title = models.CharField(max_length=255)
    content = CKEditor5Field(
        "Contenu",
        config_name="default"
    )

    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]
        verbose_name = "Section légale"
        verbose_name_plural = "Sections légales"

    def __str__(self):
        return f"{self.page.title} - {self.title}"


class LegalSidebarBlock(models.Model):
    page = models.ForeignKey(
        LegalPage,
        on_delete=models.CASCADE,
        related_name="sidebar_blocks"
    )

    title = models.CharField(max_length=255)
    content = CKEditor5Field(
        "Contenu",
        config_name="default"
    )

    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]
        verbose_name = "Bloc sidebar légal"
        verbose_name_plural = "Blocs sidebar légaux"

    def __str__(self):
        return f"{self.page.title} - {self.title}"


# ==========================================================
# CONTACT MESSAGE (SLA + ASSIGNATION)
# ==========================================================

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
    reply = models.TextField(blank=True)

    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="normal")
    sla_hours = models.PositiveIntegerField(default=48)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new")

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
        verbose_name = "Message de contact"
        verbose_name_plural = "Messages de contact"
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["priority"]),
            models.Index(fields=["created_at"]),
        ]

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

    def save(self, *args, **kwargs):

        if self.subject == "payment":
            self.priority = "high"
        elif self.subject == "complaint":
            self.priority = "urgent"

        priority_sla_map = {
            "urgent": 8,
            "high": 24,
            "normal": 48,
            "low": 72,
        }

        self.sla_hours = priority_sla_map.get(self.priority, 48)

        self.auto_assign()

        super().save(*args, **kwargs)

    @cached_property
    def deadline(self):
        return self.created_at + timezone.timedelta(hours=self.sla_hours)

    @property
    def is_overdue(self):
        if self.answered_at:
            return False
        return timezone.now() > self.deadline

    def __str__(self):
        return f"{self.full_name} - {self.get_subject_display()}"

# ==========================================================
# ABOUT PAGE — STRUCTURE SIMPLIFIÉE & STABLE
# ==========================================================




class AboutSection(models.Model):

    SECTION_CHOICES = [
        ("identity", "Identité de l’école"),
        ("vision", "Vision & Mission"),
        ("governance", "Gouvernance"),
        ("infrastructure", "Infrastructures"),
        ("student_life", "Vie étudiante"),
        ("network", "Annexes & Partenariats"),
    ]

    section_key = models.CharField(
        max_length=50,
        choices=SECTION_CHOICES,
        unique=True,
        null=True,
        blank=True
    )
    title = models.CharField(max_length=255)

    subtitle = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    content = CKEditor5Field(
        "Contenu",
        config_name="default",
        blank=True,
        null=True
    )

    image = models.ImageField(
        upload_to="about/",
        blank=True,
        null=True
    )

    highlights = models.JSONField(
        blank=True,
        null=True,
        help_text="Liste des points clés (ex: ['Reconnu par l’État', 'Système LMD'])"
    )

    icon = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Classe icône (ex: fa-solid fa-graduation-cap)"
    )

    background = models.CharField(
        max_length=50,
        default="white",
        help_text="white | light | primary"
    )

    is_active = models.BooleanField(default=True)

    order = models.PositiveIntegerField(default=0)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order"]
        verbose_name = "Section À propos"
        verbose_name_plural = "Sections À propos"

    def __str__(self):
        if self.section_key:
            return self.get_section_key_display()
        return self.title or "Section About"