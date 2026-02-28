from django.conf import settings
from django.db import models
from django.db.models import (
    UniqueConstraint,
    Index,
    Q,
)
from django.utils.text import slugify
from django.utils import timezone


# ==========================
# CATEGORY
# ==========================
class Category(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        indexes = [
            Index(fields=["slug"]),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


# ==========================
# TOPIC
# ==========================
class Topic(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, blank=True)

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="community_topics"
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="topics"
    )

    content = models.TextField()

    # Image de couverture
    cover_image = models.ImageField(
        upload_to="community/topics/%Y/%m/",
        null=True,
        blank=True
    )

    view_count = models.PositiveIntegerField(default=0)

    is_published = models.BooleanField(default=True)
    is_locked = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            Index(fields=["slug"]),
            Index(fields=["created_at"]),
            Index(fields=["category"]),
            Index(fields=["is_published"]),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1

            while Topic.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)

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

    is_accepted = models.BooleanField(default=False)

    upvotes = models.PositiveIntegerField(default=0)
    downvotes = models.PositiveIntegerField(default=0)

    is_deleted = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            Index(fields=["topic"]),
            Index(fields=["parent"]),
            Index(fields=["created_at"]),
        ]
        constraints = [
            # Une réponse acceptée doit appartenir à un topic publié
            models.CheckConstraint(
                condition=Q(is_accepted=False) | Q(topic__is_published=True),
                name="accepted_answer_requires_published_topic"
            )
        ]

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
        constraints = [
            models.CheckConstraint(
                condition=(
                    (Q(topic__isnull=False) & Q(answer__isnull=True)) |
                    (Q(topic__isnull=True) & Q(answer__isnull=False))
                ),
                name="attachment_linked_to_topic_or_answer"
            )
        ]
        indexes = [
            Index(fields=["topic"]),
            Index(fields=["answer"]),
        ]

    def __str__(self):
        return f"Fichier #{self.id} par {self.uploaded_by}"