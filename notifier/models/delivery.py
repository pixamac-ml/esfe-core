from django.db import models

from .message import NotificationMessage


class DeliveryAttempt(models.Model):
    message = models.ForeignKey(
        "notifier.NotificationMessage",
        on_delete=models.CASCADE,
        related_name="delivery_attempts",
    )
    channel = models.CharField(max_length=30, choices=NotificationMessage.CHANNEL_CHOICES)
    provider = models.CharField(max_length=50, blank=True)
    status = models.CharField(
        max_length=20,
        choices=NotificationMessage.STATUS_CHOICES,
        default=NotificationMessage.STATUS_PENDING,
    )
    attempt_count = models.PositiveIntegerField(default=0)
    provider_message_id = models.CharField(max_length=120, blank=True)
    payload_snapshot = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["provider", "status", "created_at"]),
            models.Index(fields=["channel", "status", "created_at"]),
        ]

    def __str__(self):
        return f"{self.channel}:{self.provider or 'internal'}"
