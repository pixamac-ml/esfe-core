from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class SecretaryStatusMixin(models.Model):
    STATUS_PENDING = "pending"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_TRANSFERRED = "transferred"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"
    STATUS_ARCHIVED = "archived"

    STATUS_CHOICES = [
        (STATUS_PENDING, "En attente"),
        (STATUS_IN_PROGRESS, "En cours"),
        (STATUS_TRANSFERRED, "Transfere"),
        (STATUS_COMPLETED, "Traite"),
        (STATUS_CANCELLED, "Annule"),
        (STATUS_ARCHIVED, "Archive"),
    ]

    # Table formelle des transitions de statut autorisees. Les etats
    # COMPLETED/CANCELLED ne peuvent plus que mener a ARCHIVED, et ARCHIVED
    # est terminal (coherent avec les controles deja presents dans
    # services.py : entree archivee = non reprenable).
    STATUS_TRANSITIONS = {
        STATUS_PENDING: {STATUS_IN_PROGRESS, STATUS_TRANSFERRED, STATUS_COMPLETED, STATUS_CANCELLED, STATUS_ARCHIVED},
        STATUS_IN_PROGRESS: {STATUS_PENDING, STATUS_TRANSFERRED, STATUS_COMPLETED, STATUS_CANCELLED, STATUS_ARCHIVED},
        STATUS_TRANSFERRED: {STATUS_IN_PROGRESS, STATUS_COMPLETED, STATUS_CANCELLED, STATUS_ARCHIVED},
        STATUS_COMPLETED: {STATUS_ARCHIVED},
        STATUS_CANCELLED: {STATUS_ARCHIVED},
        STATUS_ARCHIVED: set(),
    }

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    is_archived = models.BooleanField(default=False, db_index=True)

    class Meta:
        abstract = True

    def get_allowed_status_transitions(self):
        return self.STATUS_TRANSITIONS.get(self.status, set())

    def validate_status_transition(self, new_status):
        if not new_status or new_status == self.status:
            return
        if new_status not in self.get_allowed_status_transitions():
            status_labels = dict(self.STATUS_CHOICES)
            raise ValidationError({
                "status": (
                    f"Transition de statut non autorisee : "
                    f"« {status_labels.get(self.status, self.status)} » -> "
                    f"« {status_labels.get(new_status, new_status)} »."
                )
            })


class RegistryEntry(SecretaryStatusMixin):
    TYPE_PARENT_VISIT = "parent_visit"
    TYPE_SCHOOL_PAYMENT = "school_payment"
    TYPE_PACKAGE_DEPOSIT = "package_deposit"
    TYPE_SCHOOL_DELIVERY = "school_delivery"
    TYPE_APPOINTMENT_REQUEST = "appointment_request"
    TYPE_DIPLOMA_WITHDRAWAL = "diploma_withdrawal"
    TYPE_COMPLAINT = "complaint"
    TYPE_EXTERNAL_VISITOR = "external_visitor"

    ENTRY_TYPE_CHOICES = [
        (TYPE_PARENT_VISIT, "Visite parent"),
        (TYPE_SCHOOL_PAYMENT, "Paiement scolarite"),
        (TYPE_PACKAGE_DEPOSIT, "Depot colis"),
        (TYPE_SCHOOL_DELIVERY, "Livraison ecole"),
        (TYPE_APPOINTMENT_REQUEST, "Demande rendez-vous"),
        (TYPE_DIPLOMA_WITHDRAWAL, "Retrait diplome"),
        (TYPE_COMPLAINT, "Reclamation"),
        (TYPE_EXTERNAL_VISITOR, "Visiteur externe"),
    ]

    PRIORITY_LOW = "low"
    PRIORITY_NORMAL = "normal"
    PRIORITY_HIGH = "high"
    PRIORITY_IMMEDIATE = "immediate"

    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Faible"),
        (PRIORITY_NORMAL, "Normale"),
        (PRIORITY_HIGH, "Haute"),
        (PRIORITY_IMMEDIATE, "Immediate"),
    ]

    registry_number = models.CharField(max_length=40, unique=True, blank=True, null=True, db_index=True)
    daily_number = models.PositiveIntegerField(default=0, db_index=True)
    event_identifier = models.CharField(max_length=60, blank=True, db_index=True)
    branch = models.ForeignKey(
        "branches.Branch",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="secretary_registry_entries",
        db_index=True,
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    entry_type = models.CharField(max_length=100, choices=ENTRY_TYPE_CHOICES, db_index=True)
    priority = models.CharField(
        max_length=30,
        choices=PRIORITY_CHOICES,
        default=PRIORITY_NORMAL,
        db_index=True,
    )
    visitor_name = models.CharField(max_length=255, blank=True, db_index=True)
    visitor_phone = models.CharField(max_length=30, blank=True)
    visitor_email = models.EmailField(blank=True)
    student_class_label = models.CharField(max_length=120, blank=True)
    motive = models.CharField(max_length=255, blank=True)
    target_service = models.CharField(max_length=120, blank=True, db_index=True)
    workflow_code = models.CharField(max_length=80, blank=True, db_index=True)
    linked_actions = models.JSONField(default=list, blank=True)
    history = models.JSONField(default=list, blank=True)
    attachment = models.FileField(upload_to="registry_attachments/", blank=True, null=True)
    exited_at = models.DateTimeField(null=True, blank=True, db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True, db_index=True)
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
            models.Index(fields=["branch", "created_at"]),
            models.Index(fields=["entry_type", "status"]),
            models.Index(fields=["priority", "status"]),
            models.Index(fields=["related_student", "status"]),
            models.Index(fields=["created_by", "created_at"]),
        ]

    def __str__(self):
        return self.title

    def clean(self):
        if self.is_archived and self.is_active:
            self.is_active = False
        if self.closed_at and self.exited_at and self.exited_at > self.closed_at:
            raise ValidationError({"closed_at": "La cloture ne peut pas preceder l'heure de sortie."})

    def save(self, *args, **kwargs):
        if self.is_archived and self.status != self.STATUS_ARCHIVED:
            self.status = self.STATUS_ARCHIVED
        if self.related_student_id and not self.student_class_label:
            enrollment = getattr(self.related_student, "current_academic_enrollment", None)
            if enrollment and enrollment.academic_class:
                self.student_class_label = str(enrollment.academic_class)
        if not self.title:
            self.title = self.get_entry_type_display() if self.entry_type else "Entree registre"
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
