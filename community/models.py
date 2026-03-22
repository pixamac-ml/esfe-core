from django.conf import settings
from django.db import models
from django.db.models import UniqueConstraint, Index, Q
from django.utils.text import slugify
from django.utils import timezone


# ==========================
# CATEGORY (Domaine principal)
# ==========================

from django.conf import settings
from django.db import models
from django.db.models import Index
from django.utils.text import slugify


class Category(models.Model):

    # ======================
    # IDENTITÉ
    # ======================
    name = models.CharField(
        max_length=120,
        unique=True
    )

    slug = models.SlugField(
        max_length=140,
        unique=True,
        blank=True
    )

    description = models.TextField(
        blank=True
    )

    # ======================
    # ORGANISATION
    # ======================
    order = models.PositiveIntegerField(
        default=0,
        help_text="Ordre d'affichage dans la liste des catégories"
    )

    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text="Nom de l'icône (ex: bi-flask, bi-heart-pulse)"
    )

    color = models.CharField(
        max_length=20,
        blank=True,
        help_text="Couleur associée (ex: #4CAF50)"
    )

    # ======================
    # ABONNEMENTS (clé du système de notification)
    # ======================
    subscribers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="subscribed_categories",
        help_text="Utilisateurs abonnés à ce domaine"
    )

    # ======================
    # STATUT
    # ======================
    is_active = models.BooleanField(
        default=True
    )

    # ======================
    # DATES
    # ======================
    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    # ======================
    # META
    # ======================
    class Meta:
        ordering = ["order", "name"]
        indexes = [
            Index(fields=["slug"]),
            Index(fields=["is_active"]),
            Index(fields=["order"]),
        ]

    # ======================
    # MÉTHODES
    # ======================
    def save(self, *args, **kwargs):

        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1

            while Category.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)

    def topic_count(self):
        return self.topics.filter(
            is_deleted=False,
            is_published=True
        ).count()

    def subscriber_count(self):
        return self.subscribers.count()

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
from django.db import models
from django.conf import settings
from django.utils.text import slugify
from django.urls import reverse
from django.db.models import Index
from django_ckeditor_5.fields import CKEditor5Field


class Topic(models.Model):

    # ======================
    # IDENTITÉ
    # ======================
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, blank=True)
    is_pinned = models.BooleanField(default=False, verbose_name="Épinglé")
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

    # ======================
    # ORGANISATION
    # ======================
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

    # ======================
    # CONTENU RICHE
    # ======================
    content = CKEditor5Field(
        "Contenu",
        config_name="default"
    )

    cover_image = models.ImageField(
        upload_to="community/topics/%Y/%m/",
        null=True,
        blank=True
    )

    # ======================
    # ENGAGEMENT
    # ======================
    view_count = models.PositiveIntegerField(default=0)

    accepted_answer = models.ForeignKey(
        "Answer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="accepted_for_topics"
    )

    last_activity_at = models.DateTimeField(auto_now=True)

    # ======================
    # ÉTATS
    # ======================
    is_published = models.BooleanField(default=True)
    is_locked = models.BooleanField(default=False)
    is_public = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    is_edited = models.BooleanField(default=False)

    # ======================
    # DATES
    # ======================
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
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1

            while Topic.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

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



# ==========================
# NOTIFICATION
# ==========================
# ==========================
# NOTIFICATION
# ==========================
class Notification(models.Model):
    # ======================
    # TYPES DE NOTIFICATIONS
    # ======================
    TYPE_CHOICES = [
        # Nouveaux contenus
        ("new_topic", "Nouveau sujet dans votre domaine"),
        ("new_answer", "Nouvelle réponse à votre sujet"),

        # Réponses
        ("reply_to_reply", "Réponse à votre commentaire"),

        # Votes (groupés)
        ("upvote", "Nouveau(x) vote(s) sur votre contribution"),

        # Réponse acceptée
        ("accepted_answer", "Votre réponse a été acceptée"),
    ]

    # ======================
    # RELATIONS
    # ======================
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications"
    )

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="performed_actions",
        help_text="L'utilisateur qui a déclenché la notification"
    )

    topic = models.ForeignKey(
        Topic,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="notifications"
    )

    answer = models.ForeignKey(
        Answer,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="notifications"
    )

    # ======================
    # TYPE ET MÉTADONNÉES
    # ======================
    notification_type = models.CharField(
        max_length=30,
        choices=TYPE_CHOICES
    )

    # Pour grouper les votes (Option B : notifications groupées)
    vote_count = models.PositiveIntegerField(
        default=1,
        help_text="Nombre de votes agrupés (pour les notifications de type upvote)"
    )

    # Pour éviter les doublons
    is_read = models.BooleanField(default=False)

    # Pour suivre si on a déjà envoyé l'email
    email_sent = models.BooleanField(default=False)

    # ======================
    # DATES
    # ======================
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date de lecture de la notification"
    )

    # ======================
    # META
    # ======================
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            Index(fields=["user", "is_read"]),
            Index(fields=["user", "notification_type"]),
            Index(fields=["created_at"]),
            Index(fields=["topic"]),
            Index(fields=["answer"]),
        ]
        # Contrainte pour éviter les doublons de notifications
        constraints = [
            UniqueConstraint(
                fields=["user", "topic", "answer", "notification_type"],
                name="unique_notification"
            )
        ]

    # ======================
    # PROPRIÉTÉS
    # ======================
    @property
    def get_target_url(self):
        """Retourne l'URL cible de la notification"""
        from django.urls import reverse

        if self.notification_type == "new_topic" and self.topic:
            return self.topic.get_absolute_url()

        if self.notification_type in ["new_answer", "reply_to_reply", "accepted_answer"]:
            if self.answer and self.answer.topic:
                # Ajouter un anchor vers la réponse
                return f"{self.answer.topic.get_absolute_url()}#answer-{self.answer.id}"

        if self.notification_type == "upvote":
            if self.answer:
                return self.answer.topic.get_absolute_url()
            if self.topic:
                return self.topic.get_absolute_url()

        return "/"

    @property
    def get_icon(self):
        """Retourne l'icône对应的 au type de notification"""
        icons = {
            "new_topic": "📝",
            "new_answer": "💬",
            "reply_to_reply": "↩️",
            "upvote": "⬆️",
            "accepted_answer": "✅",
        }
        return icons.get(self.notification_type, "🔔")

    @property
    def get_actor_display_name(self):
        """Retourne le nom de l'acteur"""
        return self.actor.get_full_name() or self.actor.username

    # ======================
    # MÉTHODES
    # ======================
    def mark_as_read(self):
        """Marque la notification comme lue"""
        from django.utils import timezone
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=["is_read", "read_at"])

    def __str__(self):
        return f"[{self.get_notification_type_display()}] Pour {self.user.username}"



# ==========================
# SIGNALEMENT DE CONTENU
# ==========================
class Report(models.Model):
    """Signalement de contenu inapproprié"""

    REASON_CHOICES = [
        ("spam", "Spam ou publicité"),
        ("offensive", "Contenu offensant ou inapproprié"),
        ("hors_sujet", "Hors sujet"),
        ("plagiat", "Plagiat ou violation de droits d'auteur"),
        ("fausse_info", "Informations fausses ou trompeuses"),
        ("harcelement", "Harcèlement ou intimidation"),
        ("autre", "Autre"),
    ]

    STATUS_CHOICES = [
        ("pending", "En attente"),
        ("reviewing", "En cours d'examen"),
        ("resolved", "Résolu"),
        ("dismissed", "Rejeté"),
    ]

    # ======================
    # QUI SIGNALE
    # ======================
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reports_made"
    )

    # ======================
    # CE QUI EST SIGNALÉ
    # ======================
    topic = models.ForeignKey(
        Topic,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="reports"
    )

    answer = models.ForeignKey(
        Answer,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="reports"
    )

    # ======================
    # DÉTAILS DU SIGNALEMENT
    # ======================
    reason = models.CharField(
        max_length=30,
        choices=REASON_CHOICES
    )

    details = models.TextField(
        blank=True,
        help_text="Détails supplémentaires (optionnel)"
    )

    # ======================
    # TRAITEMENT
    # ======================
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reports_reviewed"
    )

    moderator_notes = models.TextField(
        blank=True,
        help_text="Notes internes du modérateur"
    )

    action_taken = models.CharField(
        max_length=100,
        blank=True,
        help_text="Action prise (ex: contenu supprimé, utilisateur averti)"
    )

    # ======================
    # DATES
    # ======================
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    # ======================
    # META
    # ======================
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            Index(fields=["status"]),
            Index(fields=["reporter"]),
            Index(fields=["created_at"]),
        ]
        # Un utilisateur ne peut signaler qu'une fois le même contenu
        constraints = [
            UniqueConstraint(
                fields=["reporter", "topic"],
                condition=Q(topic__isnull=False),
                name="unique_topic_report_per_user"
            ),
            UniqueConstraint(
                fields=["reporter", "answer"],
                condition=Q(answer__isnull=False),
                name="unique_answer_report_per_user"
            ),
        ]

    def __str__(self):
        target = self.topic.title if self.topic else f"Réponse #{self.answer.id}"
        return f"Signalement par {self.reporter.username}: {target}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if not self.topic and not self.answer:
            raise ValidationError("Le signalement doit concerner un sujet ou une réponse.")
        if self.topic and self.answer:
            raise ValidationError("Le signalement ne peut concerner qu'un seul élément.")

    def resolve(self, moderator, action="", notes=""):
        """Marque le signalement comme résolu"""
        self.status = "resolved"
        self.reviewed_by = moderator
        self.action_taken = action
        self.moderator_notes = notes
        self.resolved_at = timezone.now()
        self.save()

    def dismiss(self, moderator, notes=""):
        """Rejette le signalement"""
        self.status = "dismissed"
        self.reviewed_by = moderator
        self.moderator_notes = notes
        self.resolved_at = timezone.now()
        self.save()