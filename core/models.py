# core/models.py

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
    """
    Configuration principale de l'institution.
    Une seule instance autorisée (singleton).
    """
    name = models.CharField(max_length=255, verbose_name="Nom complet")
    short_name = models.CharField(max_length=100, blank=True, verbose_name="Nom court")

    address = models.CharField(max_length=255, verbose_name="Adresse")
    city = models.CharField(max_length=100, verbose_name="Ville")
    country = models.CharField(max_length=100, default="Mali", verbose_name="Pays")

    phone = models.CharField(max_length=50, verbose_name="Téléphone")
    email = models.EmailField(verbose_name="Email")

    is_active = models.BooleanField(default=True)

    legal_status = models.CharField(max_length=255, blank=True, verbose_name="Statut juridique")
    approval_number = models.CharField(max_length=255, blank=True, verbose_name="N° agrément")
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
# PRÉSENTATION INSTITUTIONNELLE (SINGLETON)
# ==========================================================

class InstitutionPresentation(models.Model):
    """
    Textes de présentation de l'institution.
    Une seule instance autorisée (singleton).
    """
    # Section Présentation
    about_title = models.CharField(
        max_length=255,
        default="À propos de notre institution",
        verbose_name="Titre présentation"
    )
    about_text = CKEditor5Field(
        "Texte de présentation",
        config_name="default",
        help_text="Description générale de l'école (2-3 paragraphes)"
    )
    about_image = models.ImageField(
        upload_to="institution/",
        blank=True,
        null=True,
        verbose_name="Image présentation"
    )

    # Section Vision & Mission
    vision_title = models.CharField(
        max_length=255,
        default="Notre Vision",
        verbose_name="Titre vision"
    )
    vision_text = models.TextField(
        verbose_name="Vision",
        help_text="La vision à long terme de l'institution"
    )

    mission_title = models.CharField(
        max_length=255,
        default="Notre Mission",
        verbose_name="Titre mission"
    )
    mission_text = models.TextField(
        verbose_name="Mission",
        help_text="La mission quotidienne de l'institution"
    )

    # Hero
    hero_title = models.CharField(
        max_length=255,
        default="Former les professionnels de santé de demain",
        verbose_name="Titre Hero"
    )
    hero_subtitle = models.CharField(
        max_length=500,
        default="Une institution d'excellence dédiée à la formation paramédicale et scientifique.",
        verbose_name="Sous-titre Hero"
    )
    hero_image = models.ImageField(
        upload_to="institution/hero/",
        blank=True,
        null=True,
        verbose_name="Image Hero (background)"
    )

    # CTA Final
    cta_title = models.CharField(
        max_length=255,
        default="Rejoignez une institution d'excellence",
        verbose_name="Titre CTA"
    )
    cta_subtitle = models.CharField(
        max_length=500,
        blank=True,
        default="Commencez votre parcours vers une carrière dans les sciences de la santé.",
        verbose_name="Sous-titre CTA"
    )
    cta_button_text = models.CharField(
        max_length=100,
        default="Candidater maintenant",
        verbose_name="Texte bouton CTA"
    )
    cta_button_url = models.CharField(
        max_length=255,
        default="/candidature/",
        verbose_name="URL bouton CTA"
    )

    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if InstitutionPresentation.objects.exclude(pk=self.pk).exists():
            raise ValidationError("Une seule présentation est autorisée.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return "Présentation institutionnelle"

    class Meta:
        verbose_name = "Présentation"
        verbose_name_plural = "Présentation"


# ==========================================================
# VALEURS (3-4 MAX)
# ==========================================================

class Value(models.Model):
    """
    Valeurs fondamentales de l'institution.
    Limité à 4 valeurs maximum pour rester impactant.
    """
    title = models.CharField(
        max_length=100,
        verbose_name="Titre",
        help_text="Ex: Excellence, Engagement, Innovation"
    )
    description = models.TextField(
        verbose_name="Description",
        help_text="Description courte (1-2 phrases)"
    )
    icon = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Icône",
        help_text="Classe CSS icône (ex: fa-solid fa-graduation-cap)"
    )

    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]
        verbose_name = "Valeur"
        verbose_name_plural = "Valeurs"

    def clean(self):
        # Limiter à 4 valeurs actives
        active_count = Value.objects.filter(is_active=True).exclude(pk=self.pk).count()
        if self.is_active and active_count >= 4:
            raise ValidationError("Maximum 4 valeurs actives autorisées.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


# ==========================================================
# INFRASTRUCTURES
# ==========================================================

class Infrastructure(models.Model):
    """
    Infrastructures et équipements de l'institution.
    """
    CATEGORY_CHOICES = [
        ("laboratory", "Laboratoire"),
        ("classroom", "Salle de cours"),
        ("equipment", "Équipement"),
        ("library", "Bibliothèque"),
        ("sports", "Infrastructure sportive"),
        ("other", "Autre"),
    ]

    name = models.CharField(
        max_length=150,
        verbose_name="Nom",
        help_text="Ex: Laboratoire de biologie"
    )
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default="other",
        verbose_name="Catégorie"
    )
    description = models.TextField(
        verbose_name="Description",
        help_text="Description détaillée"
    )
    image = models.ImageField(
        upload_to="infrastructure/",
        verbose_name="Photo"
    )
    features = models.JSONField(
        blank=True,
        null=True,
        verbose_name="Caractéristiques",
        help_text="Liste des équipements (ex: ['Microscopes', 'Analyseurs'])"
    )

    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]
        verbose_name = "Infrastructure"
        verbose_name_plural = "Infrastructures"

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


# ==========================================================
# PERSONNEL / STAFF
# ==========================================================

class Staff(models.Model):
    """
    Personnel de l'institution (direction, enseignants, admin).
    """
    CATEGORY_CHOICES = [
        ("direction", "Direction"),
        ("teacher", "Enseignant"),
        ("admin", "Administration"),
    ]

    # Identité
    full_name = models.CharField(
        max_length=150,
        verbose_name="Nom complet"
    )
    position = models.CharField(
        max_length=200,
        verbose_name="Poste",
        help_text="Ex: Directeur Général, Professeur de Biologie"
    )
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default="teacher",
        verbose_name="Catégorie"
    )

    # Photo
    photo = models.ImageField(
        upload_to="staff/",
        verbose_name="Photo",
        help_text="Photo professionnelle (format carré recommandé)"
    )

    # Infos optionnelles
    bio = models.TextField(
        blank=True,
        verbose_name="Biographie",
        help_text="Courte bio (optionnel)"
    )
    email = models.EmailField(
        blank=True,
        verbose_name="Email professionnel"
    )
    linkedin = models.URLField(
        blank=True,
        verbose_name="Profil LinkedIn"
    )

    # Gestion
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(
        default=False,
        verbose_name="Mis en avant",
        help_text="Afficher en priorité"
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["category", "order", "full_name"]
        verbose_name = "Personnel"
        verbose_name_plural = "Personnel"

    def __str__(self):
        return f"{self.full_name} - {self.position}"


# ==========================================================
# STATISTIQUES / CHIFFRES CLÉS
# ==========================================================

class InstitutionStat(models.Model):
    """
    Chiffres clés de l'institution (social proof).
    """
    label = models.CharField(
        max_length=100,
        verbose_name="Label",
        help_text="Ex: Étudiants formés"
    )
    value = models.PositiveIntegerField(
        verbose_name="Valeur",
        help_text="Ex: 500"
    )
    suffix = models.CharField(
        max_length=10,
        blank=True,
        verbose_name="Suffixe",
        help_text="Ex: +, %, ans"
    )
    prefix = models.CharField(
        max_length=10,
        blank=True,
        verbose_name="Préfixe",
        help_text="Ex: +"
    )

    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]
        verbose_name = "Statistique"
        verbose_name_plural = "Statistiques"

    def __str__(self):
        return f"{self.label}: {self.prefix}{self.value}{self.suffix}"


# ==========================================================
# PARTENAIRES
# ==========================================================

class Partner(models.Model):
    """
    Partenaires de l'institution (ministères, hôpitaux, organisations).
    """
    PARTNER_TYPES = [
        ("ministere", "Ministère"),
        ("hospital", "Centre Hospitalier"),
        ("international", "Organisation Internationale"),
        ("ong", "ONG"),
        ("entreprise", "Entreprise"),
        ("university", "Université"),
        ("autre", "Autre"),
    ]

    name = models.CharField(
        max_length=200,
        verbose_name="Nom du partenaire"
    )
    logo = models.ImageField(
        upload_to="partners/",
        verbose_name="Logo"
    )
    website = models.URLField(
        blank=True,
        verbose_name="Site web"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Description du partenariat"
    )
    partner_type = models.CharField(
        max_length=20,
        choices=PARTNER_TYPES,
        default="autre",
        verbose_name="Type"
    )

    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Partenaire"
        verbose_name_plural = "Partenaires"

    def __str__(self):
        return self.name


# ==========================================================
# TÉMOIGNAGES
# ==========================================================

class Testimonial(models.Model):
    """
    Témoignages des anciens étudiants/diplômés.
    """
    video_url = models.URLField(
        blank=True,
        help_text="URL YouTube ou Vimeo (ex: https://youtube.com/watch?v=...)"
    )
    video_thumbnail = models.ImageField(
        upload_to="temoignages/thumbnails/",
        blank=True,
        null=True,
        help_text="Image de prévisualisation si pas de vidéo"
    )
    quote = models.TextField(
        help_text="Le témoignage en quelques phrases"
    )
    author_name = models.CharField(
        max_length=150,
        help_text="Nom complet du diplômé"
    )
    author_role = models.CharField(
        max_length=200,
        blank=True,
        help_text="Poste actuel (ex: Directeur des ressources humaines)"
    )
    author_photo = models.ImageField(
        upload_to="temoignages/photos/",
        blank=True,
        null=True
    )
    promotion = models.CharField(
        max_length=50,
        blank=True,
        help_text="Année de promotion (ex: Promo 2019)"
    )
    programme = models.ForeignKey(
        "formations.Programme",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="testimonials",
        help_text="Formation suivie (laisser vide pour témoignage global)"
    )

    is_featured = models.BooleanField(
        default=False,
        help_text="Afficher en priorité sur la page d'accueil"
    )
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-is_featured", "order", "-pk"]
        verbose_name = "Témoignage"
        verbose_name_plural = "Témoignages"

    def __str__(self):
        return f"{self.author_name} - {self.promotion or 'Témoignage'}"


# ==========================================================
# LEGAL PAGES
# ==========================================================

class LegalPage(models.Model):

    PAGE_TYPES = (
        ("legal", "Mentions légales"),
        ("privacy", "Politique de confidentialité"),
        ("terms", "Conditions d'utilisation"),
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
    content = CKEditor5Field("Contenu", config_name="default")

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
    content = CKEditor5Field("Contenu", config_name="default")

    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]
        verbose_name = "Bloc sidebar légal"
        verbose_name_plural = "Blocs sidebar légaux"

    def __str__(self):
        return f"{self.page.title} - {self.title}"


# ==========================================================
# CONTACT MESSAGE
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
# NOTIFICATIONS
# ==========================================================

class Notification(models.Model):
    """
    Notifications automatiques pour les candidats.
    """
    TYPE_CHOICES = [
        ("candidature_submitted", "Candidature soumise"),
        ("candidature_under_review", "Candidature en cours d'analyse"),
        ("candidature_to_complete", "Candidature à compléter"),
        ("candidature_accepted", "Candidature acceptée"),
        ("candidature_accepted_with_reserve", "Candidature acceptée sous réserve"),
        ("candidature_rejected", "Candidature refusée"),
        ("inscription_created", "Inscription créée"),
        ("inscription_active", "Inscription active"),
        ("payment_received", "Paiement reçu"),
        ("payment_validated", "Paiement validé"),
        ("document_missing", "Document manquant"),
    ]

    recipient_email = models.EmailField()
    recipient_name = models.CharField(max_length=150)

    notification_type = models.CharField(max_length=50, choices=TYPE_CHOICES)

    title = models.CharField(max_length=200)
    message = models.TextField()

    related_candidature = models.ForeignKey(
        "admissions.Candidature",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications"
    )

    related_inscription = models.ForeignKey(
        "inscriptions.Inscription",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications"
    )

    related_payment = models.ForeignKey(
        "payments.Payment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications"
    )

    email_sent = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        indexes = [
            models.Index(fields=["notification_type"]),
            models.Index(fields=["recipient_email"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.get_notification_type_display()} - {self.recipient_email}"


# ==========================================================
# HISTORIQUE DES STATUTS
# ==========================================================

class StatusHistory(models.Model):
    """
    Historique des changements de statut pour les candidatures.
    """
    candidature = models.ForeignKey(
        "admissions.Candidature",
        on_delete=models.CASCADE,
        related_name="status_history"
    )

    old_status = models.CharField(max_length=30)
    new_status = models.CharField(max_length=30)

    changed_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="status_changes"
    )

    comment = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Historique de statut"
        verbose_name_plural = "Historique des statuts"

    def __str__(self):
        return f"{self.candidature.full_name}: {self.old_status} -> {self.new_status}"
