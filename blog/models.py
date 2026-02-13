from django.db import models
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.db.models import Count


# ==========================================================
# CATEGORY
# ==========================================================

class Category(models.Model):
    name = models.CharField(max_length=150, unique=True)
    slug = models.SlugField(max_length=160, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Catégorie"
        verbose_name_plural = "Catégories"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("blog:category_detail", args=[self.slug])

    def __str__(self):
        return self.name


# ==========================================================
# ARTICLE MANAGER
# ==========================================================

class PublishedManager(models.Manager):
    def get_queryset(self):
        return (
            super().get_queryset()
            .filter(status='published', is_deleted=False)
        )


# ==========================================================
# ARTICLE
# ==========================================================

class Article(models.Model):

    STATUS_CHOICES = (
        ('draft', 'Brouillon'),
        ('published', 'Publié'),
        ('archived', 'Archivé'),
    )

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)

    excerpt = models.TextField()
    content = models.TextField()

    # IMAGE PRINCIPALE
    featured_image = models.ImageField(
        upload_to='blog/featured/',
        blank=True,
        null=True
    )

    # SEO
    meta_title = models.CharField(max_length=255, blank=True)
    meta_description = models.TextField(blank=True)

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='articles'
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='articles'
    )

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='draft'
    )

    allow_comments = models.BooleanField(default=True)
    published_at = models.DateTimeField(null=True, blank=True)

    views_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_deleted = models.BooleanField(default=False)

    objects = models.Manager()
    published = PublishedManager()

    class Meta:
        ordering = ['-published_at']
        indexes = [
            models.Index(fields=['status', 'published_at']),
            models.Index(fields=['slug']),
        ]
        verbose_name = "Article"
        verbose_name_plural = "Articles"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)

        if self.status == 'published' and not self.published_at:
            self.published_at = timezone.now()

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("blog:article_detail", args=[self.slug])

    def get_meta_title(self):
        return self.meta_title if self.meta_title else self.title

    def get_meta_description(self):
        return self.meta_description if self.meta_description else self.excerpt

    def __str__(self):
        return self.title


# ==========================================================
# ARTICLE IMAGE (GALERIE)
# ==========================================================

class ArticleImage(models.Model):
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name='images'
    )
    image = models.ImageField(upload_to='blog/gallery/')
    caption = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Image d'article"
        verbose_name_plural = "Images d'articles"

    def __str__(self):
        return f"Image - {self.article.title}"


# ==========================================================
# COMMENT
# ==========================================================

class Comment(models.Model):

    STATUS_CHOICES = (
        ('pending', 'En attente'),
        ('approved', 'Approuvé'),
        ('rejected', 'Rejeté'),
    )

    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name='comments'
    )

    author_name = models.CharField(max_length=150)
    author_email = models.EmailField(blank=True, null=True)
    content = models.TextField()

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = "Commentaire"
        verbose_name_plural = "Commentaires"

    def __str__(self):
        return f"{self.author_name} - {self.article.title}"


# ==========================================================
# COMMENT LIKE
# ==========================================================

class CommentLike(models.Model):
    comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        related_name='likes'
    )
    ip_address = models.GenericIPAddressField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('comment', 'ip_address')
        verbose_name = "Like"
        verbose_name_plural = "Likes"

    def __str__(self):
        return f"Like - {self.comment.id}"
