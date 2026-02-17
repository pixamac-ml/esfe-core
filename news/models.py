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

    program = models.ForeignKey(
        Program,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="news"
    )

    image = models.ImageField(upload_to="news/main/", blank=True, null=True)

    categorie = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="news"
    )

    # Publication
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    auteur = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="news_posts")
    published_at = models.DateTimeField(null=True, blank=True)

    # Indicateurs éditoriaux
    is_important = models.BooleanField(default=False)
    is_urgent = models.BooleanField(default=False)

    # Statistiques
    views_count = models.PositiveIntegerField(default=0)

    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


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


