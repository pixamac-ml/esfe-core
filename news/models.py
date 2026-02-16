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


# --------------------------------------------------
# NEWS
# --------------------------------------------------
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

    # Contenu
    titre = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)

    resume = models.TextField(blank=True)
    contenu = models.TextField()

    image = models.ImageField(
        upload_to="news/main/",
        blank=True,
        null=True
    )

    categorie = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="news"
    )

    # Publication
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

    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-created_at"]
        verbose_name = "Actualité"
        verbose_name_plural = "Actualités"
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["published_at"]),
            models.Index(fields=["slug"]),
        ]

    def __str__(self):
        return self.titre

    # --------------------------------------------------
    # URL PROPRE
    # --------------------------------------------------
    def get_absolute_url(self):
        return reverse("news:detail", kwargs={"slug": self.slug})

    # --------------------------------------------------
    # ÉTAT PUBLICATION
    # --------------------------------------------------
    @property
    def is_published(self):
        return (
            self.status == self.STATUS_PUBLISHED
            and self.published_at
            and self.published_at <= timezone.now()
        )

    # --------------------------------------------------
    # SAVE OVERRIDE
    # --------------------------------------------------
    def save(self, *args, **kwargs):

        if not self.slug:
            base_slug = slugify(self.titre)
            slug = base_slug
            counter = 1

            while News.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        if self.image:
            self.image = optimize_image(
                self.image,
                max_width=1600,
                quality=75
            )

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
