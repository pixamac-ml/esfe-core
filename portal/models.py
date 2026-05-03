from __future__ import annotations

from django.conf import settings
from django.db import models

from branches.models import Branch


class SupportAuditLog(models.Model):
    ACTION_PASSWORD_RESET = "password_reset"
    ACTION_ACCOUNT_ACTIVATED = "account_activated"
    ACTION_ACCOUNT_DEACTIVATED = "account_deactivated"
    ACTION_DIAGNOSTIC_VIEWED = "diagnostic_viewed"
    ACTION_TICKET_CREATED = "ticket_created"
    ACTION_TICKET_ASSIGNED = "ticket_assigned"
    ACTION_TICKET_STATUS_CHANGED = "ticket_status_changed"
    ACTION_TICKET_COMMENTED = "ticket_commented"
    ACTION_ACCOUNT_SUSPENDED = "account_suspended"
    ACTION_ACCOUNT_REACTIVATED = "account_reactivated"
    ACTION_ACCOUNT_UNBLOCKED = "account_unblocked"
    ACTION_EMAIL_UPDATED = "email_updated"
    ACTION_GRADE_UPDATED = "grade_updated"
    ACTION_GRADES_IMPORTED = "grades_imported"
    ACTION_BRANCH_SETTINGS_UPDATED = "branch_settings_updated"

    ACTION_CHOICES = [
        (ACTION_PASSWORD_RESET, "Reinitialisation mot de passe"),
        (ACTION_ACCOUNT_ACTIVATED, "Activation compte"),
        (ACTION_ACCOUNT_DEACTIVATED, "Desactivation compte"),
        (ACTION_DIAGNOSTIC_VIEWED, "Diagnostic consulte"),
        (ACTION_TICKET_CREATED, "Ticket cree"),
        (ACTION_TICKET_ASSIGNED, "Ticket assigne"),
        (ACTION_TICKET_STATUS_CHANGED, "Statut ticket modifie"),
        (ACTION_TICKET_COMMENTED, "Commentaire ticket"),
        (ACTION_ACCOUNT_SUSPENDED, "Compte suspendu"),
        (ACTION_ACCOUNT_REACTIVATED, "Compte reactive"),
        (ACTION_ACCOUNT_UNBLOCKED, "Compte debloque"),
        (ACTION_EMAIL_UPDATED, "Email corrige"),
        (ACTION_GRADE_UPDATED, "Note modifiee"),
        (ACTION_GRADES_IMPORTED, "Import notes"),
        (ACTION_BRANCH_SETTINGS_UPDATED, "Parametres annexe modifies"),
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


class SupportTicket(models.Model):
    STATUS_OPEN = "open"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_RESOLVED = "resolved"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_OPEN, "Ouvert"),
        (STATUS_IN_PROGRESS, "En cours"),
        (STATUS_RESOLVED, "Resolu"),
        (STATUS_REJECTED, "Rejete"),
    ]

    PRIORITY_LOW = "low"
    PRIORITY_NORMAL = "normal"
    PRIORITY_HIGH = "high"
    PRIORITY_CRITICAL = "critical"

    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Basse"),
        (PRIORITY_NORMAL, "Normale"),
        (PRIORITY_HIGH, "Haute"),
        (PRIORITY_CRITICAL, "Critique"),
    ]

    CATEGORY_ACCOUNT = "account"
    CATEGORY_DOCUMENT = "document"
    CATEGORY_GRADES = "grades"
    CATEGORY_STUDENT = "student"
    CATEGORY_OTHER = "other"

    CATEGORY_CHOICES = [
        (CATEGORY_ACCOUNT, "Compte"),
        (CATEGORY_DOCUMENT, "Document"),
        (CATEGORY_GRADES, "Notes"),
        (CATEGORY_STUDENT, "Etudiant"),
        (CATEGORY_OTHER, "Autre"),
    ]

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="support_tickets",
        db_index=True,
    )
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default=CATEGORY_OTHER, db_index=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default=PRIORITY_NORMAL, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN, db_index=True)
    requester_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_support_tickets",
    )
    student = models.ForeignKey(
        "students.Student",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_tickets",
    )
    inscription = models.ForeignKey(
        "inscriptions.Inscription",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_tickets",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_support_tickets",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_support_tickets",
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_support_tickets",
    )
    resolution = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Ticket support"
        verbose_name_plural = "Tickets support"
        indexes = [
            models.Index(fields=["branch", "status", "created_at"]),
            models.Index(fields=["assigned_to", "status", "created_at"]),
            models.Index(fields=["category", "status", "created_at"]),
        ]

    def __str__(self):
        return f"#{self.pk} - {self.title}"


class SupportTicketComment(models.Model):
    ticket = models.ForeignKey(
        SupportTicket,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="support_ticket_comments",
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "Commentaire ticket support"
        verbose_name_plural = "Commentaires tickets support"

    def __str__(self):
        return f"Commentaire ticket #{self.ticket_id}"


class AccountSupportState(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="support_state",
    )
    is_suspended = models.BooleanField(default=False, db_index=True)
    is_blocked = models.BooleanField(default=False, db_index=True)
    must_change_password = models.BooleanField(default=False, db_index=True)
    failed_login_count = models.PositiveSmallIntegerField(default=0)
    blocked_until = models.DateTimeField(null=True, blank=True, db_index=True)
    note = models.TextField(blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_account_support_states",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Etat support compte"
        verbose_name_plural = "Etats support comptes"
        indexes = [
            models.Index(fields=["is_suspended", "is_blocked"]),
            models.Index(fields=["must_change_password"]),
        ]

    def __str__(self):
        return f"Etat support de {self.user}"


class BranchITSettings(models.Model):
    branch = models.OneToOneField(
        Branch,
        on_delete=models.CASCADE,
        related_name="it_settings",
    )
    validation_threshold = models.DecimalField(max_digits=4, decimal_places=2, default=10)
    active_academic_year = models.CharField(max_length=20, blank=True)
    local_config = models.TextField(blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_branch_it_settings",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Parametres informaticien annexe"
        verbose_name_plural = "Parametres informaticien annexes"

    def __str__(self):
        return f"Parametres IT - {self.branch}"
