from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import slugify
from django.urls import reverse

from core.images.optimizer import optimize_image
from .managers import PublishedNewsManager

User = get_user_model()


# --------------------------------------------------
# CATEGORY
# --------------------------------------------------
class Category(models.Model):
    nom = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    ordre = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["ordre", "nom"]
        verbose_name = "Catégorie"
        verbose_name_plural = "Catégories"

    def __str__(self):
        return self.nom


class Program(models.Model):
    nom = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    image = models.ImageField(upload_to="programs/", blank=True, null=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom

# --------------------------------------------------
# NEWS
# --------------------------------------------------
# --------------------------------------------------
# NEWS
# --------------------------------------------------
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import slugify
from django.urls import reverse

from core.images.optimizer import optimize_image
from .managers import PublishedNewsManager

User = get_user_model()


from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import slugify
from django.urls import reverse

from .managers import PublishedNewsManager

User = get_user_model()


class News(models.Model):

    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_ARCHIVED = "archived"

    STATUS_CHOICES = (
        (STATUS_DRAFT, "Brouillon"),
        (STATUS_PUBLISHED, "Publié"),
        (STATUS_ARCHIVED, "Archivé"),
    )

    objects = models.Manager()
    published = PublishedNewsManager()

    # ==========================
    # CONTENU
    # ==========================
    titre = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    resume = models.TextField(blank=True)
    contenu = models.TextField()

    program = models.ForeignKey(
        "Program",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="news"
    )

    image = models.ImageField(upload_to="news/main/", blank=True, null=True)

    categorie = models.ForeignKey(
        "Category",
        on_delete=models.PROTECT,
        related_name="news"
    )

    # ==========================
    # PUBLICATION
    # ==========================
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT
    )

    auteur = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="news_posts"
    )

    published_at = models.DateTimeField(null=True, blank=True)

    # ==========================
    # INDICATEURS
    # ==========================
    is_important = models.BooleanField(default=False)
    is_urgent = models.BooleanField(default=False)

    # ==========================
    # STATISTIQUES
    # ==========================
    views_count = models.PositiveIntegerField(default=0)

    # ==========================
    # MÉTADONNÉES
    # ==========================
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ======================================================
    # MÉTHODES MÉTIER
    # ======================================================

    def __str__(self):
        return self.titre

    def get_absolute_url(self):
        return reverse("news:detail", kwargs={"slug": self.slug})

    def generate_unique_slug(self):
        """
        Génère un slug ASCII propre, sans caractères spéciaux,
        sans accents, et garanti unique.
        """
        base_slug = slugify(self.titre, allow_unicode=False)

        if not base_slug:
            base_slug = "news"

        slug = base_slug
        counter = 1

        while News.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

        return slug

    def save(self, *args, **kwargs):

        # Toujours régénérer si slug invalide ou vide
        if not self.slug:
            self.slug = self.generate_unique_slug()
        else:
            # Sécurise les anciens slugs corrompus
            cleaned_slug = slugify(self.slug, allow_unicode=False)
            if cleaned_slug != self.slug:
                self.slug = self.generate_unique_slug()

        # Auto date publication
        if self.status == self.STATUS_PUBLISHED and not self.published_at:
            self.published_at = timezone.now()

        super().save(*args, **kwargs)


# --------------------------------------------------
# NEWS GALLERY
# --------------------------------------------------
class NewsImage(models.Model):
    news = models.ForeignKey(
        News,
        on_delete=models.CASCADE,
        related_name="gallery"
    )

    image = models.ImageField(upload_to="news/gallery/")
    ordre = models.PositiveIntegerField(default=0)
    alt_text = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["ordre"]
        verbose_name = "Image d’actualité"
        verbose_name_plural = "Images d’actualité"

    def __str__(self):
        return f"Image - {self.news.titre}"

    def save(self, *args, **kwargs):
        if self.image:
            self.image = optimize_image(
                self.image,
                max_width=1600,
                quality=75
            )
        super().save(*args, **kwargs)


