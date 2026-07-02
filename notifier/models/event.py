from django.conf import settings
from django.db import models


class NotificationEvent(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PROCESSED = "processed"
    STATUS_PARTIAL = "partial"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSED, "Processed"),
        (STATUS_PARTIAL, "Partial"),
        (STATUS_FAILED, "Failed"),
    ]

    event_type = models.CharField(max_length=120)
    source_app = models.CharField(max_length=80, default="core")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notification_events_emitted",
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notification_events_received",
    )
    payload = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event_type"]),
            models.Index(fields=["source_app", "created_at"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["recipient", "created_at"]),
        ]

    def __str__(self):
        return f"{self.event_type} [{self.source_app}]"
