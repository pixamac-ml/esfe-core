from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class SecretaryStatusMixin(models.Model):
    STATUS_PENDING = "pending"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "En attente"),
        (STATUS_IN_PROGRESS, "En cours"),
        (STATUS_COMPLETED, "Termine"),
        (STATUS_CANCELLED, "Annule"),
    ]

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    is_archived = models.BooleanField(default=False, db_index=True)

    class Meta:
        abstract = True


class RegistryEntry(SecretaryStatusMixin):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    entry_type = models.CharField(max_length=100, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="registry_entries_created",
    )
    related_student = models.ForeignKey(
        "students.Student",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registry_entries",
    )
    related_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registry_entries_staff",
    )
    status = models.CharField(
        max_length=50,
        choices=SecretaryStatusMixin.STATUS_CHOICES,
        default=SecretaryStatusMixin.STATUS_PENDING,
        db_index=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["related_student", "status"]),
            models.Index(fields=["created_by", "created_at"]),
        ]

    def __str__(self):
        return self.title

    def clean(self):
        if self.is_archived and self.is_active:
            self.is_active = False

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Appointment(SecretaryStatusMixin):
    title = models.CharField(max_length=255)
    person_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    reason = models.TextField(blank=True)
    scheduled_at = models.DateTimeField(db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="appointments_created",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointments_assigned",
    )
    related_student = models.ForeignKey(
        "students.Student",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointments",
    )
    related_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointments_related_staff",
    )
    status = models.CharField(
        max_length=50,
        choices=SecretaryStatusMixin.STATUS_CHOICES,
        default=SecretaryStatusMixin.STATUS_PENDING,
        db_index=True,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["scheduled_at", "title"]
        indexes = [
            models.Index(fields=["status", "scheduled_at"]),
            models.Index(fields=["assigned_to", "scheduled_at"]),
            models.Index(fields=["related_student", "scheduled_at"]),
        ]

    def __str__(self):
        return f"{self.title} - {self.person_name}"

    def clean(self):
        errors = {}

        if self.scheduled_at and self.scheduled_at < timezone.now():
            errors["scheduled_at"] = "Un rendez-vous ne peut pas etre planifie dans le passe."

        if self.is_archived and self.is_active:
            self.is_active = False

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class VisitorLog(SecretaryStatusMixin):
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=30, blank=True)
    reason = models.TextField(blank=True)
    related_student = models.ForeignKey(
        "students.Student",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="visitor_logs",
    )
    related_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="visitor_logs_staff",
    )
    arrived_at = models.DateTimeField(db_index=True)
    departed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    status = models.CharField(
        max_length=50,
        choices=SecretaryStatusMixin.STATUS_CHOICES,
        default=SecretaryStatusMixin.STATUS_IN_PROGRESS,
        db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="visitor_logs_created",
    )

    class Meta:
        ordering = ["-arrived_at"]
        indexes = [
            models.Index(fields=["status", "arrived_at"]),
            models.Index(fields=["related_student", "arrived_at"]),
            models.Index(fields=["related_staff", "arrived_at"]),
        ]

    def __str__(self):
        return self.full_name

    def clean(self):
        errors = {}

        if self.departed_at and self.arrived_at and self.departed_at < self.arrived_at:
            errors["departed_at"] = "La date de depart ne peut pas etre anterieure a l'arrivee."

        if self.status == self.STATUS_COMPLETED and not self.departed_at:
            errors["status"] = "Une visite terminee doit avoir une heure de depart."

        if self.is_archived and self.is_active:
            self.is_active = False

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class DocumentReceipt(SecretaryStatusMixin):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    submitted_by_name = models.CharField(max_length=255)
    submitted_by_phone = models.CharField(max_length=30, blank=True)
    related_student = models.ForeignKey(
        "students.Student",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_receipts",
    )
    related_registry = models.ForeignKey(
        RegistryEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
    )
    status = models.CharField(
        max_length=50,
        choices=SecretaryStatusMixin.STATUS_CHOICES,
        default=SecretaryStatusMixin.STATUS_PENDING,
        db_index=True,
    )
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="document_receipts_received",
    )
    file = models.FileField(upload_to="document_receipts/", blank=True, null=True)

    class Meta:
        ordering = ["-received_at"]
        indexes = [
            models.Index(fields=["status", "received_at"]),
            models.Index(fields=["related_student", "received_at"]),
            models.Index(fields=["related_registry", "received_at"]),
        ]

    def __str__(self):
        return self.title

    def clean(self):
        if self.is_archived and self.is_active:
            self.is_active = False

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class SecretaryTask(SecretaryStatusMixin):
    PRIORITY_LOW = "low"
    PRIORITY_MEDIUM = "medium"
    PRIORITY_HIGH = "high"
    PRIORITY_URGENT = "urgent"

    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Faible"),
        (PRIORITY_MEDIUM, "Moyenne"),
        (PRIORITY_HIGH, "Haute"),
        (PRIORITY_URGENT, "Urgente"),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    priority = models.CharField(
        max_length=50,
        choices=PRIORITY_CHOICES,
        default=PRIORITY_MEDIUM,
        db_index=True,
    )
    status = models.CharField(
        max_length=50,
        choices=SecretaryStatusMixin.STATUS_CHOICES,
        default=SecretaryStatusMixin.STATUS_PENDING,
        db_index=True,
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="secretary_tasks_assigned",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="secretary_tasks_created",
    )
    related_student = models.ForeignKey(
        "students.Student",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="secretary_tasks",
    )
    due_date = models.DateField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["status", "due_date", "-created_at"]
        indexes = [
            models.Index(fields=["status", "priority"]),
            models.Index(fields=["assigned_to", "status"]),
            models.Index(fields=["related_student", "status"]),
        ]

    def __str__(self):
        return self.title

    def clean(self):
        if self.is_archived and self.is_active:
            self.is_active = False

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
