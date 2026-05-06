from django.conf import settings
from django.db import models


def conversation_attachment_upload_path(instance, filename):
    return f"communication/conversations/{instance.message.conversation_id}/{filename}"


class Conversation(models.Model):
    TYPE_DIRECT = "direct"
    TYPE_GROUP = "group"
    TYPE_SUPPORT = "support"
    TYPE_SYSTEM = "system"

    TYPE_CHOICES = [
        (TYPE_DIRECT, "Direct"),
        (TYPE_GROUP, "Group"),
        (TYPE_SUPPORT, "Support"),
        (TYPE_SYSTEM, "System"),
    ]

    STATUS_ACTIVE = "active"
    STATUS_ARCHIVED = "archived"
    STATUS_CLOSED = "closed"

    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_ARCHIVED, "Archived"),
        (STATUS_CLOSED, "Closed"),
    ]

    subject = models.CharField(max_length=255, blank=True)
    conversation_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_DIRECT)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_conversations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["conversation_type", "status"]),
            models.Index(fields=["updated_at"]),
        ]

    def __str__(self):
        return self.subject or f"Conversation #{self.pk}"


class ConversationParticipant(models.Model):
    ROLE_MEMBER = "member"
    ROLE_ADMIN = "admin"
    ROLE_SYSTEM = "system"

    ROLE_CHOICES = [
        (ROLE_MEMBER, "Member"),
        (ROLE_ADMIN, "Admin"),
        (ROLE_SYSTEM, "System"),
    ]

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversation_participations",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    notifications_muted = models.BooleanField(default=False)
    last_read_at = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("conversation", "user")]
        indexes = [
            models.Index(fields=["user", "joined_at"]),
            models.Index(fields=["conversation", "role"]),
        ]

    def __str__(self):
        return f"{self.user} in {self.conversation}"


class ConversationMessage(models.Model):
    TYPE_TEXT = "text"
    TYPE_SYSTEM = "system"
    TYPE_EVENT = "event"

    TYPE_CHOICES = [
        (TYPE_TEXT, "Text"),
        (TYPE_SYSTEM, "System"),
        (TYPE_EVENT, "Event"),
    ]

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="conversation_messages",
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="replies",
    )
    message_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_TEXT)
    body = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
            models.Index(fields=["author", "created_at"]),
        ]

    def __str__(self):
        return f"Message #{self.pk} in {self.conversation_id}"


class MessageAttachment(models.Model):
    message = models.ForeignKey(
        ConversationMessage,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(upload_to=conversation_attachment_upload_path)
    original_name = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.original_name or self.file.name


class MessageReadReceipt(models.Model):
    message = models.ForeignKey(
        ConversationMessage,
        on_delete=models.CASCADE,
        related_name="read_receipts",
    )
    participant = models.ForeignKey(
        ConversationParticipant,
        on_delete=models.CASCADE,
        related_name="read_receipts",
    )
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("message", "participant")]
        indexes = [models.Index(fields=["participant", "read_at"])]

    def __str__(self):
        return f"Read {self.message_id} by {self.participant_id}"
