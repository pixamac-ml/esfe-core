from __future__ import annotations

from django.conf import settings
from django.db import models

from branches.models import Branch


class SupportAuditLog(models.Model):
    ACTION_PASSWORD_RESET = "password_reset"
    ACTION_ACCOUNT_ACTIVATED = "account_activated"
    ACTION_ACCOUNT_DEACTIVATED = "account_deactivated"
    ACTION_DIAGNOSTIC_VIEWED = "diagnostic_viewed"

    ACTION_CHOICES = [
        (ACTION_PASSWORD_RESET, "Reinitialisation mot de passe"),
        (ACTION_ACCOUNT_ACTIVATED, "Activation compte"),
        (ACTION_ACCOUNT_DEACTIVATED, "Desactivation compte"),
        (ACTION_DIAGNOSTIC_VIEWED, "Diagnostic consulte"),
    ]

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="support_audit_logs",
        db_index=True,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="performed_support_audit_logs",
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="targeted_support_audit_logs",
    )
    action_type = models.CharField(max_length=30, choices=ACTION_CHOICES, db_index=True)
    target_label = models.CharField(max_length=255, blank=True)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Journal support"
        verbose_name_plural = "Journal support"
        indexes = [
            models.Index(fields=["branch", "created_at"]),
            models.Index(fields=["actor", "created_at"]),
            models.Index(fields=["action_type", "created_at"]),
        ]

    def __str__(self):
        return f"{self.get_action_type_display()} - {self.target_label or self.target_user_id or '-'}"
