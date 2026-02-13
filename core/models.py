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
