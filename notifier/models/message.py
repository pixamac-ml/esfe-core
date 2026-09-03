import uuid

from django.conf import settings
from django.db import models


class NotificationMessage(models.Model):
    CHANNEL_IN_APP = "in_app"
    CHANNEL_EMAIL_TRANSACTIONAL = "email_transactional"
    CHANNEL_EMAIL_MARKETING = "email_marketing"
    CHANNEL_WEBSOCKET = "websocket"
    CHANNEL_SMS_FUTURE = "sms_future"

    CHANNEL_CHOICES = [
        (CHANNEL_IN_APP, "In-app"),
        (CHANNEL_EMAIL_TRANSACTIONAL, "Email transactionnel"),
        (CHANNEL_EMAIL_MARKETING, "Email marketing"),
        (CHANNEL_WEBSOCKET, "WebSocket"),
        (CHANNEL_SMS_FUTURE, "SMS futur"),
    ]

    PRIORITY_LOW = "low"
    PRIORITY_NORMAL = "normal"
    PRIORITY_HIGH = "high"
    PRIORITY_CRITICAL = "critical"

    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Low"),
        (PRIORITY_NORMAL, "Normal"),
        (PRIORITY_HIGH, "High"),
        (PRIORITY_CRITICAL, "Critical"),
    ]

    STATUS_PENDING = "pending"
    STATUS_QUEUED = "queued"
    STATUS_SENT = "sent"
    STATUS_DELIVERED = "delivered"
    STATUS_READ = "read"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_QUEUED, "Queued"),
        (STATUS_SENT, "Sent"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_READ, "Read"),
        (STATUS_FAILED, "Failed"),
        (STATUS_SKIPPED, "Skipped"),
    ]

    event = models.ForeignKey(
        "notifier.NotificationEvent",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="messages",
    )
    batch_id = models.UUIDField(null=True, blank=True, db_index=True)
    thread_id = models.UUIDField(null=True, blank=True, db_index=True)
    parent_message = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="replies",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notifier_messages_sent",
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="notifier_messages",
    )
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    notification_type = models.CharField(max_length=100)
    event_type = models.CharField(max_length=120)
    channel = models.CharField(max_length=30, choices=CHANNEL_CHOICES)
    priority = models.CharField(
        max_length=12,
        choices=PRIORITY_CHOICES,
        default=PRIORITY_NORMAL,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    metadata = models.JSONField(default=dict, blank=True)
    legacy_source = models.CharField(max_length=80, blank=True)
    legacy_object_id = models.CharField(max_length=64, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)
    pinned_at = models.DateTimeField(null=True, blank=True, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "status", "created_at"]),
            models.Index(fields=["channel", "status", "created_at"]),
            models.Index(fields=["event_type", "created_at"]),
            models.Index(fields=["legacy_source", "legacy_object_id"]),
            models.Index(
                fields=["recipient", "channel", "archived_at", "created_at"],
                name="notifier_rec_chan_arch_idx",
            ),
        ]

    def __str__(self):
        return f"{self.title} -> {self.recipient or 'external'}"


def internal_message_attachment_upload_path(instance, filename):
    owner_id = instance.uploaded_by_id or "unknown"
    return f"notifier/internal-messages/{owner_id}/{instance.batch_id}/{filename}"


class MessageAttachment(models.Model):
    batch_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="internal_message_attachments",
    )
    file = models.FileField(upload_to=internal_message_attachment_upload_path)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    size = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return self.original_name

    @property
    def is_image(self):
        """Indique si la pièce jointe peut être prévisualisée sans téléchargement."""
        content_type = (self.content_type or "").lower()
        if content_type.startswith("image/"):
            return True
        return self.original_name.lower().endswith((".jpg", ".jpeg", ".png"))
