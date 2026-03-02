from django.conf import settings
from django.db import models
from django.db.models import UniqueConstraint, Index
from django.utils.text import slugify
from django.utils import timezone


# ==========================
# CATEGORY (Domaine principal)
# ==========================
class Category(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "name"]
        indexes = [Index(fields=["slug"])]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


# ==========================
# TAG (Sous-thèmes dynamiques)
# ==========================
class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    usage_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


from django.urls import reverse

from django.conf import settings
from django.db import models
from django.db.models import UniqueConstraint, Index
from django.utils.text import slugify
from django.utils import timezone
from django.urls import reverse
from django_ckeditor_5.fields import CKEditor5Field


# ==========================
# TOPIC
# ==========================
class Topic(models.Model):

    # ----------------------
    # Identité
    # ----------------------
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, blank=True)

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="community_topics"
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_topics"
    )

    # ----------------------
    # Organisation
    # ----------------------
    category = models.ForeignKey(
        "Category",
        on_delete=models.PROTECT,
        related_name="topics"
    )

    tags = models.ManyToManyField(
        "Tag",
        blank=True,
        related_name="topics"
    )

    # ----------------------
    # Contenu riche
    # ----------------------
    content = CKEditor5Field(
        "Contenu",
        config_name="default"
    )

    cover_image = models.ImageField(
        upload_to="community/topics/%Y/%m/",
        null=True,
        blank=True
    )

    # ----------------------
    # Engagement
    # ----------------------
    view_count = models.PositiveIntegerField(default=0)

    accepted_answer = models.ForeignKey(
        "Answer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="accepted_for_topics"
    )

    last_activity_at = models.DateTimeField(auto_now=True)

    # ----------------------
    # États logiques
    # ----------------------
    is_published = models.BooleanField(default=True)
    is_locked = models.BooleanField(default=False)
    is_public = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    is_edited = models.BooleanField(default=False)

    # ----------------------
    # Dates
    # ----------------------
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ======================
    # META
    # ======================
    class Meta:
        ordering = ["-last_activity_at"]
        indexes = [
            Index(fields=["slug"]),
            Index(fields=["created_at"]),
            Index(fields=["category"]),
            Index(fields=["author"]),
            Index(fields=["is_published"]),
            Index(fields=["is_deleted"]),
            Index(fields=["last_activity_at"]),
        ]

    # ======================
    # MÉTHODES
    # ======================

    def save(self, *args, **kwargs):
        # Génération automatique du slug
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1

            while Topic.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        # Marquer comme édité si modification
        if self.pk:
            original = Topic.objects.filter(pk=self.pk).first()
            if original and original.content != self.content:
                self.is_edited = True

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse(
            "community:topic_detail",
            kwargs={"slug": self.slug}
        )

    def soft_delete(self):
        self.is_deleted = True
        self.is_published = False
        self.save(update_fields=["is_deleted", "is_published"])

    def restore(self):
        self.is_deleted = False
        self.is_published = True
        self.save(update_fields=["is_deleted", "is_published"])

    def __str__(self):
        return self.title

# ==========================
# ANSWER
# ==========================
class Answer(models.Model):
    topic = models.ForeignKey(
        Topic,
        on_delete=models.CASCADE,
        related_name="answers"
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="community_answers"
    )

    content = models.TextField()

    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="replies"
    )

    upvotes = models.PositiveIntegerField(default=0)
    downvotes = models.PositiveIntegerField(default=0)

    is_deleted = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-upvotes", "created_at"]
        indexes = [
            Index(fields=["topic"]),
            Index(fields=["parent"]),
            Index(fields=["created_at"]),
        ]

    @property
    def score(self):
        return self.upvotes - self.downvotes

    def __str__(self):
        return f"Réponse #{self.id} par {self.author}"


# ==========================
# VOTE
# ==========================
class Vote(models.Model):
    UPVOTE = 1
    DOWNVOTE = -1

    VOTE_CHOICES = (
        (UPVOTE, "Upvote"),
        (DOWNVOTE, "Downvote"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    answer = models.ForeignKey(
        Answer,
        on_delete=models.CASCADE,
        related_name="votes"
    )

    value = models.SmallIntegerField(choices=VOTE_CHOICES)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["user", "answer"],
                name="unique_user_answer_vote"
            )
        ]
        indexes = [
            Index(fields=["answer"]),
            Index(fields=["user"]),
        ]

    def __str__(self):
        return f"{self.user} vote {self.value}"


# ==========================
# TOPIC VIEW (Anti-refresh abuse)
# ==========================
class TopicView(models.Model):
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )
    ip_address = models.GenericIPAddressField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            Index(fields=["topic"]),
            Index(fields=["user"]),
            Index(fields=["ip_address"]),
        ]


# ==========================
# ATTACHMENT
# ==========================
def attachment_upload_path(instance, filename):
    return f"community/attachments/{timezone.now().year}/{filename}"


class Attachment(models.Model):
    topic = models.ForeignKey(
        Topic,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="attachments"
    )

    answer = models.ForeignKey(
        Answer,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="attachments"
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    file = models.FileField(upload_to=attachment_upload_path)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            Index(fields=["topic"]),
            Index(fields=["answer"]),
        ]

    def clean(self):
        if not self.topic and not self.answer:
            raise ValueError("Le fichier doit être lié à un topic ou une réponse.")
        if self.topic and self.answer:
            raise ValueError("Le fichier ne peut pas être lié aux deux.")

    def __str__(self):
        return f"Fichier #{self.id} par {self.uploaded_by}"