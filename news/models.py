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




# actualites/models.py

class ResultSession(models.Model):

    TYPE_CHOICES = (
        ("semestre", "Résultat semestriel"),
        ("examen", "Examen national"),
    )

    type = models.CharField(max_length=20, choices=TYPE_CHOICES)

    titre = models.CharField(max_length=255)

    annee_academique = models.CharField(max_length=20)

    annexe = models.CharField(max_length=150)
    filiere = models.CharField(max_length=150)
    classe = models.CharField(max_length=150)

    fichier_pdf = models.FileField(
        upload_to="resultats/pdf/"
    )

    is_published = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-annee_academique", "-created_at"]

    def __str__(self):
        return f"{self.get_type_display()} - {self.classe} - {self.annee_academique}"




from django.db import models
from django.utils.text import slugify
from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image
from io import BytesIO
import os


# ==========================================================
# TYPE D'ÉVÉNEMENT
# ==========================================================

class EventType(models.Model):
    name = models.CharField(max_length=150)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Type d'événement"
        verbose_name_plural = "Types d'événements"

    def __str__(self):
        return self.name


# ==========================================================
# EVENT
# ==========================================================

class Event(models.Model):

    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)

    event_type = models.ForeignKey(
        EventType,
        on_delete=models.PROTECT,
        related_name="events"
    )

    description = models.TextField(blank=True)

    event_date = models.DateField()
    cover_image = models.ImageField(upload_to="events/covers/", blank=True)
    cover_thumbnail = models.ImageField(upload_to="events/covers/thumbs/", blank=True)

    is_published = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-event_date"]
        indexes = [
            models.Index(fields=["event_date"]),
            models.Index(fields=["slug"]),
        ]

    def save(self, *args, **kwargs):

        if not self.slug:
            self.slug = slugify(self.title)

        super().save(*args, **kwargs)

        # Optimisation de la cover
        if self.cover_image:
            self._process_image("cover_image", "cover_thumbnail")

    def _process_image(self, image_field, thumb_field):

        image = getattr(self, image_field)

        if not image:
            return

        img = Image.open(image)

        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # HD optimisée
        hd_buffer = BytesIO()
        img.thumbnail((1600, 1200), Image.LANCZOS)
        img.save(hd_buffer, format="WEBP", quality=85)

        hd_name = os.path.splitext(image.name)[0] + ".webp"
        getattr(self, image_field).save(hd_name, ContentFile(hd_buffer.getvalue()), save=False)

        # Thumbnail
        thumb_img = img.copy()
        thumb_img.thumbnail((500, 350), Image.LANCZOS)

        thumb_buffer = BytesIO()
        thumb_img.save(thumb_buffer, format="WEBP", quality=75)

        thumb_name = os.path.splitext(image.name)[0] + "_thumb.webp"
        getattr(self, thumb_field).save(thumb_name, ContentFile(thumb_buffer.getvalue()), save=False)

        super().save(update_fields=[image_field, thumb_field])

    def media_count(self):
        return self.media_items.count()

    def image_count(self):
        return self.media_items.filter(media_type="image").count()

    def video_count(self):
        return self.media_items.filter(media_type="video").count()

    def __str__(self):
        return self.title


# ==========================================================
# MEDIA ITEM
# ==========================================================

class MediaItem(models.Model):

    IMAGE = "image"
    VIDEO = "video"

    TYPE_CHOICES = (
        (IMAGE, "Image"),
        (VIDEO, "Vidéo"),
    )

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="media_items"
    )

    media_type = models.CharField(max_length=10, choices=TYPE_CHOICES)

    image = models.ImageField(upload_to="events/media/", blank=True, null=True)
    thumbnail = models.ImageField(upload_to="events/media/thumbs/", blank=True, null=True)

    video_url = models.URLField(blank=True, null=True)

    caption = models.CharField(max_length=255, blank=True)

    is_featured = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["media_type"]),
            models.Index(fields=["created_at"]),
        ]

    def save(self, *args, **kwargs):

        super().save(*args, **kwargs)

        if self.media_type == "image" and self.image:
            self._process_image()

    def _process_image(self):

        img = Image.open(self.image)

        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # HD optimisée
        hd_buffer = BytesIO()
        img.thumbnail((1600, 1200), Image.LANCZOS)
        img.save(hd_buffer, format="WEBP", quality=85)

        hd_name = os.path.splitext(self.image.name)[0] + ".webp"
        self.image.save(hd_name, ContentFile(hd_buffer.getvalue()), save=False)

        # Thumbnail rapide
        thumb_img = img.copy()
        thumb_img.thumbnail((400, 300), Image.LANCZOS)

        thumb_buffer = BytesIO()
        thumb_img.save(thumb_buffer, format="WEBP", quality=70)

        thumb_name = os.path.splitext(self.image.name)[0] + "_thumb.webp"
        self.thumbnail.save(thumb_name, ContentFile(thumb_buffer.getvalue()), save=False)

        super().save(update_fields=["image", "thumbnail"])

    def __str__(self):
        return f"{self.event.title} - {self.media_type}"