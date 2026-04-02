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
from django.core.exceptions import ValidationError
from PIL import Image
from io import BytesIO
import os
import subprocess
from django.conf import settings


# ==========================================================
# CONFIGURATION FFMPEG
# ==========================================================

# En production, on peut fournir FFMPEG_PATH (ex: /usr/bin/ffmpeg)
FFMPEG_PATH = getattr(settings, "FFMPEG_PATH", "ffmpeg")

# Profils qualite image (galerie events)
EVENT_IMAGE_MAX_SIZE = (2400, 2400)
EVENT_COVER_THUMB_SIZE = (960, 720)
EVENT_MEDIA_THUMB_SIZE = (960, 960)
EVENT_FULL_QUALITY = 92
EVENT_THUMB_QUALITY = 86


# ==========================================================
# TYPE D'ÉVÉNEMENT
# ==========================================================

class EventType(models.Model):
    name = models.CharField(max_length=150)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

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

    def save(self, *args, **kwargs):

        if not self.slug:
            self.slug = slugify(self.title)

        super().save(*args, **kwargs)

        if self.cover_image and not self.cover_thumbnail:
            self._process_cover()

    def _process_cover(self):

        img = Image.open(self.cover_image)

        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # On duplique avant redimensionnement pour garder une base propre.
        original = img.copy()

        base_name = os.path.basename(self.cover_image.name)
        file_root = os.path.splitext(base_name)[0]

        # Full quality (hero/detail)
        buffer_hd = BytesIO()
        full = original.copy()
        full.thumbnail(EVENT_IMAGE_MAX_SIZE, Image.LANCZOS)
        full.save(
            buffer_hd,
            format="WEBP",
            quality=EVENT_FULL_QUALITY,
            method=6,
            optimize=True,
        )

        self.cover_image.save(
            f"{file_root}.webp",
            ContentFile(buffer_hd.getvalue()),
            save=False
        )

        # Thumbnail premium (listes/cartes)
        thumb = original.copy()
        thumb.thumbnail(EVENT_COVER_THUMB_SIZE, Image.LANCZOS)

        buffer_thumb = BytesIO()
        thumb.save(
            buffer_thumb,
            format="WEBP",
            quality=EVENT_THUMB_QUALITY,
            method=6,
            optimize=True,
        )

        self.cover_thumbnail.save(
            f"{file_root}_thumb.webp",
            ContentFile(buffer_thumb.getvalue()),
            save=False
        )

        super().save(update_fields=["cover_image", "cover_thumbnail"])

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

    video_file = models.FileField(upload_to="events/videos/", blank=True, null=True)
    video_url = models.URLField(blank=True, null=True)

    caption = models.CharField(max_length=255, blank=True)
    is_featured = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    # =========================
    # VALIDATION
    # =========================

    def clean(self):
        if self.video_file and self.video_file.size > 300 * 1024 * 1024:
            raise ValidationError("La vidéo ne doit pas dépasser 300MB.")

    # =========================
    # SAVE
    # =========================

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        if self.media_type == self.IMAGE and self.image and not self.thumbnail:
            self._process_image()

        # Evite une recompression video a chaque edition.
        if self.media_type == self.VIDEO and self.video_file and not self.thumbnail:
            self._process_video()

    # =========================
    # IMAGE PROCESSING
    # =========================

    def _process_image(self):

        img = Image.open(self.image)

        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        original = img.copy()

        base_name = os.path.basename(self.image.name)
        file_root = os.path.splitext(base_name)[0]

        # Full quality (lightbox/detail)
        buffer_hd = BytesIO()
        full = original.copy()
        full.thumbnail(EVENT_IMAGE_MAX_SIZE, Image.LANCZOS)
        full.save(
            buffer_hd,
            format="WEBP",
            quality=EVENT_FULL_QUALITY,
            method=6,
            optimize=True,
        )

        self.image.save(
            f"{file_root}.webp",
            ContentFile(buffer_hd.getvalue()),
            save=False
        )

        # Thumbnail premium (grilles galerie)
        thumb = original.copy()
        thumb.thumbnail(EVENT_MEDIA_THUMB_SIZE, Image.LANCZOS)

        buffer_thumb = BytesIO()
        thumb.save(
            buffer_thumb,
            format="WEBP",
            quality=EVENT_THUMB_QUALITY,
            method=6,
            optimize=True,
        )

        self.thumbnail.save(
            f"{file_root}_thumb.webp",
            ContentFile(buffer_thumb.getvalue()),
            save=False
        )

        super().save(update_fields=["image", "thumbnail"])

    # =========================
    # VIDEO PROCESSING (FFMPEG)
    # =========================

    def _process_video(self):

        # Accepte un binaire present dans le PATH systeme (prod Linux/Windows).
        ffmpeg_bin = FFMPEG_PATH

        input_path = self.video_file.path
        base = os.path.splitext(input_path)[0]

        compressed_path = f"{base}_compressed.mp4"
        thumbnail_path = f"{base}_thumb.jpg"

        try:
            # Compression vidéo
            subprocess.run([
                ffmpeg_bin,
                "-i", input_path,
                "-vcodec", "libx264",
                "-crf", "23",
                "-preset", "medium",
                "-acodec", "aac",
                compressed_path
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # Génération thumbnail
            subprocess.run([
                ffmpeg_bin,
                "-i", input_path,
                "-ss", "00:00:01",
                "-vframes", "1",
                thumbnail_path
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            return

        if os.path.exists(compressed_path):
            os.remove(input_path)
            os.rename(compressed_path, input_path)

        if os.path.exists(thumbnail_path):
            with open(thumbnail_path, "rb") as f:
                self.thumbnail.save(
                    os.path.basename(thumbnail_path),
                    ContentFile(f.read()),
                    save=False
                )
            os.remove(thumbnail_path)

        super().save(update_fields=["thumbnail"])

    # =========================
    # YOUTUBE EMBED SAFE
    # =========================

    def get_embed_url(self):

        if not self.video_url:
            return None

        if "watch?v=" in self.video_url:
            vid = self.video_url.split("v=")[-1].split("&")[0]
            return f"https://www.youtube.com/embed/{vid}"

        if "youtu.be/" in self.video_url:
            vid = self.video_url.split("/")[-1]
            return f"https://www.youtube.com/embed/{vid}"

        return self.video_url

    def __str__(self):
        return f"{self.event.title} - {self.media_type}"