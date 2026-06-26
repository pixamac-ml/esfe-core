import secrets
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from . import constants


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BranchAcademicCycle(TimeStampedModel):
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="academic_cycles")
    academic_year = models.ForeignKey("academics.AcademicYear", on_delete=models.PROTECT, related_name="branch_cycles")
    status = models.CharField(
        max_length=30,
        choices=constants.BRANCH_CYCLE_STATUS_CHOICES,
        default=constants.BRANCH_CYCLE_DRAFT,
        db_index=True,
    )
    registration_open_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    deliberation_started_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    activated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activated_branch_cycles",
    )
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_branch_cycles",
    )
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="archived_branch_cycles",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-academic_year__start_date", "branch__name"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "academic_year"], name="academic_cycle_unique_branch_year"),
        ]
        indexes = [
            models.Index(fields=["branch", "academic_year"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.branch} - {self.academic_year} ({self.status})"


class ClassCycleStatus(TimeStampedModel):
    branch_cycle = models.ForeignKey(BranchAcademicCycle, on_delete=models.CASCADE, related_name="class_statuses")
    academic_class = models.ForeignKey("academics.AcademicClass", on_delete=models.PROTECT, related_name="cycle_statuses")
    status = models.CharField(
        max_length=40,
        choices=constants.CLASS_CYCLE_STATUS_CHOICES,
        default=constants.CLASS_TEACHING,
        db_index=True,
    )
    semester_1_done = models.BooleanField(default=False)
    semester_2_done = models.BooleanField(default=False)
    grades_done = models.BooleanField(default=False)
    bulletins_done = models.BooleanField(default=False)
    has_blocking_anomaly = models.BooleanField(default=False)
    readiness_score = models.PositiveSmallIntegerField(default=0)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checked_class_cycle_statuses",
    )

    class Meta:
        ordering = ["academic_class__programme__title", "academic_class__level"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch_cycle", "academic_class"],
                name="academic_cycle_unique_class_status_per_cycle",
            ),
        ]
        indexes = [
            models.Index(fields=["branch_cycle", "status"]),
            models.Index(fields=["academic_class", "status"]),
        ]

    def clean(self):
        if self.academic_class_id and self.branch_cycle_id:
            if self.academic_class.branch_id != self.branch_cycle.branch_id:
                raise ValidationError({"academic_class": "La classe ne correspond pas a l'annexe du cycle."})
            if self.academic_class.academic_year_id != self.branch_cycle.academic_year_id:
                raise ValidationError({"academic_class": "La classe ne correspond pas a l'annee du cycle."})

    def __str__(self):
        return f"{self.academic_class} - {self.status}"


class AcademicClosureReport(models.Model):
    branch_cycle = models.ForeignKey(BranchAcademicCycle, on_delete=models.CASCADE, related_name="closure_reports")
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_closure_reports",
    )
    status = models.CharField(
        max_length=20,
        choices=constants.CLOSURE_REPORT_STATUS_CHOICES,
        default=constants.CLOSURE_REPORT_DRAFT,
        db_index=True,
    )
    total_classes = models.PositiveIntegerField(default=0)
    completed_classes = models.PositiveIntegerField(default=0)
    blocked_classes = models.PositiveIntegerField(default=0)
    missing_grades_count = models.PositiveIntegerField(default=0)
    anomaly_count = models.PositiveIntegerField(default=0)
    bulletin_missing_count = models.PositiveIntegerField(default=0)
    financial_summary_snapshot = models.JSONField(default=dict, blank=True)
    academic_summary_snapshot = models.JSONField(default=dict, blank=True)
    details = models.JSONField(default=dict, blank=True)
    generated_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-generated_at", "-id"]
        indexes = [
            models.Index(fields=["branch_cycle", "status"]),
            models.Index(fields=["generated_at"]),
        ]

    def __str__(self):
        return f"Rapport {self.branch_cycle} - {self.status}"


class StudentYearDecision(TimeStampedModel):
    student = models.ForeignKey("students.Student", on_delete=models.CASCADE, related_name="cycle_year_decisions")
    academic_year = models.ForeignKey("academics.AcademicYear", on_delete=models.PROTECT, related_name="cycle_student_decisions")
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="cycle_student_decisions")
    current_class = models.ForeignKey(
        "academics.AcademicClass",
        on_delete=models.PROTECT,
        related_name="cycle_decisions_as_current",
    )
    target_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cycle_student_decisions_as_target",
    )
    target_class = models.ForeignKey(
        "academics.AcademicClass",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cycle_decisions_as_target",
    )
    decision = models.CharField(
        max_length=40,
        choices=constants.STUDENT_DECISION_CHOICES,
        default=constants.DECISION_PENDING,
        db_index=True,
    )
    reason = models.TextField(blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cycle_student_decisions_made",
    )
    decided_at = models.DateTimeField(default=timezone.now, db_index=True)
    is_final = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["-decided_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["student", "academic_year"], name="academic_cycle_unique_decision_student_year"),
        ]
        indexes = [
            models.Index(fields=["branch", "academic_year", "decision"]),
            models.Index(fields=["student", "is_final"]),
        ]

    def clean(self):
        if self.current_class_id and self.branch_id and self.current_class.branch_id != self.branch_id:
            raise ValidationError({"current_class": "La classe courante ne correspond pas a l'annexe."})
        if self.current_class_id and self.academic_year_id and self.current_class.academic_year_id != self.academic_year_id:
            raise ValidationError({"current_class": "La classe courante ne correspond pas a l'annee source."})
        if self.target_class_id and self.target_year_id and self.target_class.academic_year_id != self.target_year_id:
            raise ValidationError({"target_class": "La classe cible ne correspond pas a l'annee cible."})

    def __str__(self):
        return f"{self.student} - {self.academic_year} - {self.decision}"


class StudentAcademicDebt(TimeStampedModel):
    student = models.ForeignKey("students.Student", on_delete=models.CASCADE, related_name="academic_cycle_debts")
    source_academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.PROTECT,
        related_name="academic_cycle_debts_as_source",
    )
    source_class = models.ForeignKey(
        "academics.AcademicClass",
        on_delete=models.PROTECT,
        related_name="academic_cycle_debts_as_source",
    )
    current_academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="academic_cycle_debts_as_current",
    )
    current_class = models.ForeignKey(
        "academics.AcademicClass",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="academic_cycle_debts_as_current",
    )
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="academic_cycle_debts")
    debt_type = models.CharField(max_length=20, choices=constants.ACADEMIC_DEBT_TYPE_CHOICES, db_index=True)
    semester_label = models.CharField(max_length=40, blank=True)
    ue = models.ForeignKey("academics.UE", on_delete=models.PROTECT, null=True, blank=True, related_name="academic_cycle_debts")
    ec = models.ForeignKey("academics.EC", on_delete=models.PROTECT, null=True, blank=True, related_name="academic_cycle_debts")
    required_credits = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    earned_credits = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    missing_credits = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    validation_threshold = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("10.00"))
    status = models.CharField(
        max_length=20,
        choices=constants.ACADEMIC_DEBT_STATUS_CHOICES,
        default=constants.DEBT_PENDING,
        db_index=True,
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True)

    class Meta:
        ordering = ["student", "source_academic_year", "status"]
        indexes = [
            models.Index(fields=["branch", "source_academic_year", "status"]),
            models.Index(fields=["student", "status"]),
        ]

    def save(self, *args, **kwargs):
        if self.missing_credits is None:
            self.missing_credits = max(self.required_credits - self.earned_credits, Decimal("0.00"))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} - dette {self.debt_type} ({self.status})"


class AcademicDebtEvaluationSession(TimeStampedModel):
    SESSION_VACATION = "vacation"
    SESSION_YEARLY = "yearly"
    SESSION_SPECIAL = "special"
    SESSION_TYPE_CHOICES = [
        (SESSION_VACATION, "Vacances"),
        (SESSION_YEARLY, "Annuelle"),
        (SESSION_SPECIAL, "Speciale"),
    ]
    STATUS_PLANNED = "planned"
    STATUS_OPEN = "open"
    STATUS_CLOSED = "closed"
    STATUS_VALIDATED = "validated"
    STATUS_CHOICES = [
        (STATUS_PLANNED, "Planifiee"),
        (STATUS_OPEN, "Ouverte"),
        (STATUS_CLOSED, "Fermee"),
        (STATUS_VALIDATED, "Validee"),
    ]

    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="academic_debt_sessions")
    academic_year = models.ForeignKey("academics.AcademicYear", on_delete=models.PROTECT, related_name="academic_debt_sessions")
    title = models.CharField(max_length=180)
    session_type = models.CharField(max_length=20, choices=SESSION_TYPE_CHOICES, default=SESSION_SPECIAL)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PLANNED, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_academic_debt_sessions",
    )

    class Meta:
        ordering = ["-starts_at"]
        indexes = [models.Index(fields=["branch", "academic_year", "status"])]

    def clean(self):
        if self.starts_at and self.ends_at and self.starts_at >= self.ends_at:
            raise ValidationError({"ends_at": "La fin doit etre posterieure au debut."})

    def __str__(self):
        return self.title


class AcademicDebtEvaluation(TimeStampedModel):
    debt = models.ForeignKey(StudentAcademicDebt, on_delete=models.CASCADE, related_name="evaluations")
    session = models.ForeignKey(AcademicDebtEvaluationSession, on_delete=models.PROTECT, related_name="evaluations")
    student = models.ForeignKey("students.Student", on_delete=models.CASCADE, related_name="academic_debt_evaluations")
    grade = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    is_validated = models.BooleanField(default=False, db_index=True)
    validated_at = models.DateTimeField(null=True, blank=True)
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="validated_academic_debt_evaluations",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["student", "is_validated"])]

    def save(self, *args, **kwargs):
        if self.is_validated and not self.validated_at:
            self.validated_at = timezone.now()
        super().save(*args, **kwargs)


class StudentFinancialPosition(TimeStampedModel):
    student = models.ForeignKey("students.Student", on_delete=models.CASCADE, related_name="financial_positions")
    academic_year = models.ForeignKey("academics.AcademicYear", on_delete=models.PROTECT, related_name="student_financial_positions")
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="student_financial_positions")
    previous_debt_amount = models.PositiveBigIntegerField(default=0)
    current_year_due_amount = models.PositiveBigIntegerField(default=0)
    current_year_paid_amount = models.PositiveBigIntegerField(default=0)
    total_due_amount = models.PositiveBigIntegerField(default=0)
    total_paid_amount = models.PositiveBigIntegerField(default=0)
    remaining_amount = models.PositiveBigIntegerField(default=0)
    status = models.CharField(
        max_length=30,
        choices=constants.FINANCIAL_STATUS_CHOICES,
        default=constants.FINANCIAL_CLEAR,
        db_index=True,
    )
    last_computed_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["student", "-academic_year__start_date"]
        constraints = [
            models.UniqueConstraint(fields=["student", "academic_year"], name="academic_cycle_unique_financial_position"),
        ]
        indexes = [
            models.Index(fields=["branch", "academic_year", "status"]),
            models.Index(fields=["student", "status"]),
        ]

    def __str__(self):
        return f"{self.student} - {self.remaining_amount} FCFA"


class StudentAccessPolicy(TimeStampedModel):
    student = models.ForeignKey("students.Student", on_delete=models.CASCADE, related_name="access_policies")
    academic_year = models.ForeignKey("academics.AcademicYear", on_delete=models.PROTECT, related_name="student_access_policies")
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="student_access_policies")
    access_level = models.CharField(max_length=40, choices=constants.ACCESS_LEVEL_CHOICES, default=constants.ACCESS_LIMITED)
    can_access_dashboard = models.BooleanField(default=True)
    can_access_courses = models.BooleanField(default=False)
    can_access_schedule = models.BooleanField(default=False)
    can_download_bulletin = models.BooleanField(default=False)
    can_download_transcript = models.BooleanField(default=False)
    can_download_certificate = models.BooleanField(default=False)
    can_download_diploma = models.BooleanField(default=False)
    reason = models.TextField(blank=True)
    computed_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["student", "-academic_year__start_date"]
        constraints = [
            models.UniqueConstraint(fields=["student", "academic_year"], name="academic_cycle_unique_access_policy"),
        ]
        indexes = [
            models.Index(fields=["branch", "academic_year", "access_level"]),
            models.Index(fields=["student", "access_level"]),
        ]

    def __str__(self):
        return f"{self.student} - {self.access_level}"


class AcademicReEnrollment(TimeStampedModel):
    STATUS_PREPARED = "prepared"
    STATUS_NOTIFIED = "notified"
    STATUS_STARTED = "started"
    STATUS_PENDING_PAYMENT = "pending_payment"
    STATUS_PAYMENT_VALIDATED = "payment_validated"
    STATUS_ACTIVATED = "activated"
    STATUS_CANCELLED = "cancelled"
    STATUS_TRANSFER_REQUESTED = "transfer_requested"
    STATUS_ABANDONED = "abandoned"
    STATUS_CHOICES = [
        (STATUS_PREPARED, "Preparee"),
        (STATUS_NOTIFIED, "Notifiee"),
        (STATUS_STARTED, "Demarree"),
        (STATUS_PENDING_PAYMENT, "Paiement attendu"),
        (STATUS_PAYMENT_VALIDATED, "Paiement valide"),
        (STATUS_ACTIVATED, "Activee"),
        (STATUS_CANCELLED, "Annulee"),
        (STATUS_TRANSFER_REQUESTED, "Transfert demande"),
        (STATUS_ABANDONED, "Abandon"),
    ]

    student = models.ForeignKey("students.Student", on_delete=models.CASCADE, related_name="academic_reenrollments")
    source_academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.PROTECT,
        related_name="academic_reenrollments_as_source",
    )
    target_academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.PROTECT,
        related_name="academic_reenrollments_as_target",
    )
    source_class = models.ForeignKey(
        "academics.AcademicClass",
        on_delete=models.PROTECT,
        related_name="academic_reenrollments_as_source",
    )
    target_class = models.ForeignKey(
        "academics.AcademicClass",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="academic_reenrollments_as_target",
    )
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="academic_reenrollments")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_PREPARED, db_index=True)
    token = models.CharField(max_length=80, unique=True, db_index=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    prepared_by_system = models.BooleanField(default=True)
    started_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    payment_validated_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "target_academic_year"],
                name="academic_cycle_unique_reenrollment_student_target_year",
            ),
        ]
        indexes = [
            models.Index(fields=["branch", "target_academic_year", "status"]),
            models.Index(fields=["student", "status"]),
        ]

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} - {self.target_academic_year} ({self.status})"


class TransferRequest(TimeStampedModel):
    STATUS_DRAFT = "draft"
    STATUS_SUBMITTED = "submitted"
    STATUS_UNDER_REVIEW = "under_review"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Brouillon"),
        (STATUS_SUBMITTED, "Soumise"),
        (STATUS_UNDER_REVIEW, "En etude"),
        (STATUS_APPROVED, "Approuvee"),
        (STATUS_REJECTED, "Rejetee"),
        (STATUS_CANCELLED, "Annulee"),
    ]

    student = models.ForeignKey("students.Student", on_delete=models.CASCADE, related_name="transfer_requests")
    source_academic_year = models.ForeignKey("academics.AcademicYear", on_delete=models.PROTECT, related_name="transfer_requests_as_source")
    target_academic_year = models.ForeignKey("academics.AcademicYear", on_delete=models.PROTECT, related_name="transfer_requests_as_target")
    source_branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="transfer_requests_as_source")
    target_branch = models.ForeignKey(
        "branches.Branch",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="transfer_requests_as_target",
    )
    source_class = models.ForeignKey("academics.AcademicClass", on_delete=models.PROTECT, related_name="transfer_requests_as_source")
    requested_programme = models.ForeignKey(
        "formations.Programme",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="transfer_requests",
    )
    requested_class = models.ForeignKey(
        "academics.AcademicClass",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="transfer_requests_as_requested",
    )
    requested_branch = models.ForeignKey(
        "branches.Branch",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="transfer_requests_as_requested",
    )
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="academic_cycle_reviewed_transfer_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["source_branch", "status"]),
            models.Index(fields=["target_academic_year", "status"]),
            models.Index(fields=["student", "status"]),
        ]

    def __str__(self):
        return f"Transfert {self.student} - {self.status}"


class AcademicCorrectionRequest(TimeStampedModel):
    TYPE_IDENTITY_ERROR = "identity_error"
    TYPE_GRADE_ERROR = "grade_error"
    TYPE_BULLETIN_ERROR = "bulletin_error"
    TYPE_TRANSCRIPT_ERROR = "transcript_error"
    TYPE_DIPLOMA_ERROR = "diploma_error"
    TYPE_OTHER = "other"
    TYPE_CHOICES = [
        (TYPE_IDENTITY_ERROR, "Erreur identite"),
        (TYPE_GRADE_ERROR, "Erreur note"),
        (TYPE_BULLETIN_ERROR, "Erreur bulletin"),
        (TYPE_TRANSCRIPT_ERROR, "Erreur releve"),
        (TYPE_DIPLOMA_ERROR, "Erreur diplome"),
        (TYPE_OTHER, "Autre"),
    ]
    STATUS_SUBMITTED = "submitted"
    STATUS_ASSIGNED = "assigned"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_RESOLVED = "resolved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_SUBMITTED, "Soumise"),
        (STATUS_ASSIGNED, "Assignee"),
        (STATUS_IN_PROGRESS, "En cours"),
        (STATUS_RESOLVED, "Resolue"),
        (STATUS_REJECTED, "Rejetee"),
    ]

    student = models.ForeignKey(
        "students.Student",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="academic_correction_requests",
    )
    academic_year = models.ForeignKey("academics.AcademicYear", on_delete=models.PROTECT, related_name="academic_correction_requests")
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="academic_correction_requests")
    academic_class = models.ForeignKey(
        "academics.AcademicClass",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="academic_correction_requests",
    )
    request_type = models.CharField(max_length=30, choices=TYPE_CHOICES, db_index=True)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SUBMITTED, db_index=True)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="submitted_academic_corrections")
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_academic_corrections",
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_academic_corrections",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["branch", "academic_year", "status"]),
            models.Index(fields=["request_type", "status"]),
        ]

    def __str__(self):
        return f"Correction {self.request_type} - {self.status}"


class AcademicAuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="academic_cycle_audit_logs",
    )
    branch = models.ForeignKey(
        "branches.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="academic_cycle_audit_logs",
    )
    academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="academic_cycle_audit_logs",
    )
    student = models.ForeignKey(
        "students.Student",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="academic_cycle_audit_logs",
    )
    action = models.CharField(max_length=80, db_index=True)
    object_type = models.CharField(max_length=120, db_index=True)
    object_id = models.CharField(max_length=80, db_index=True)
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField(null=True, blank=True)
    reason = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["branch", "academic_year", "created_at"]),
            models.Index(fields=["student", "created_at"]),
            models.Index(fields=["action", "created_at"]),
        ]

    def __str__(self):
        return f"{self.action} {self.object_type}#{self.object_id}"


class GradeModificationRequest(TimeStampedModel):
    """Demande de correction d'une note EC apres cloture de sa session.

    Meme principe que `accounts.models.SensitiveActionRequest` (paiements) :
    la saisie normale n'est jamais bloquee par ce workflow. Il s'active
    uniquement quand un informaticien/gestionnaire tente de CORRIGER une
    note deja saisie dans une session (normale ou rattrapage) deja cloturee.
    Un code OTP est alors envoye au Directeur des Etudes (ou a defaut a la
    direction executive) et la correction n'est appliquee qu'apres saisie du
    bon code, dans le delai imparti.
    """

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_EXPIRED = "expired"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "En attente"),
        (STATUS_APPROVED, "Approuvee"),
        (STATUS_EXPIRED, "Expiree"),
        (STATUS_CANCELLED, "Annulee"),
    ]

    SESSION_NORMAL = "normal"
    SESSION_RETAKE = "retake"
    SESSION_CHOICES = [
        (SESSION_NORMAL, "Normale"),
        (SESSION_RETAKE, "Rattrapage"),
    ]

    OTP_VALIDITY_MINUTES = 5

    branch = models.ForeignKey("branches.Branch", on_delete=models.CASCADE, related_name="grade_modification_requests")
    ec_grade = models.ForeignKey(
        "academics.ECGrade",
        on_delete=models.CASCADE,
        related_name="modification_requests",
    )
    session_type = models.CharField(max_length=10, choices=SESSION_CHOICES)

    previous_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    requested_score = models.DecimalField(max_digits=5, decimal_places=2)
    reason = models.TextField(blank=True)

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="grade_modification_requests",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_grade_modifications",
    )

    otp_code_hash = models.CharField(max_length=128)
    attempts = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    expires_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Demande de correction de note"
        verbose_name_plural = "Demandes de correction de note"
        indexes = [
            models.Index(fields=["branch", "status"]),
            models.Index(fields=["ec_grade", "status"]),
        ]

    def __str__(self):
        return f"Correction note #{self.ec_grade_id} ({self.get_status_display()})"

    @property
    def is_expired(self):
        return self.status == self.STATUS_PENDING and timezone.now() > self.expires_at
