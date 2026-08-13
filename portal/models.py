from __future__ import annotations

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from academics.models import AcademicClass, AcademicYear, EC, Semester, UE
from branches.models import Branch


def teacher_document_upload_path(instance, filename):
    teacher_id = instance.teacher_id or "unknown"
    branch_id = instance.branch_id or "unknown"
    return f"portal/teachers/{branch_id}/{teacher_id}/{filename}"


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
    ACTION_RESULTS_CALCULATED = "results_calculated"
    ACTION_RESULTS_SENT = "results_sent_director"
    ACTION_EXCEL_EXPORTED = "excel_exported"
    ACTION_STUDENT_CARD_GENERATED = "student_card_generated"
    ACTION_BRANCH_SETTINGS_UPDATED = "branch_settings_updated"
    ACTION_REENROLLMENT_PROPOSED = "reenrollment_proposed"
    ACTION_REENROLLMENT_VALIDATED = "reenrollment_validated"
    ACTION_REENROLLMENT_APPLIED = "reenrollment_applied"
    ACTION_REENROLLMENT_REJECTED = "reenrollment_rejected"

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
        (ACTION_RESULTS_CALCULATED, "Resultats calcules"),
        (ACTION_RESULTS_SENT, "Resultats envoyes direction"),
        (ACTION_EXCEL_EXPORTED, "Export Excel"),
        (ACTION_STUDENT_CARD_GENERATED, "Carte etudiant generee"),
        (ACTION_BRANCH_SETTINGS_UPDATED, "Parametres annexe modifies"),
        (ACTION_REENROLLMENT_PROPOSED, "Passage propose"),
        (ACTION_REENROLLMENT_VALIDATED, "Passage valide"),
        (ACTION_REENROLLMENT_APPLIED, "Passage applique"),
        (ACTION_REENROLLMENT_REJECTED, "Passage rejete"),
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


class ArchiveBatch(models.Model):
    TYPE_CLASS = "class"
    TYPE_YEAR = "year"
    TYPE_CHOICES = [
        (TYPE_CLASS, "Classe"),
        (TYPE_YEAR, "Annee academique"),
    ]

    STATUS_ARCHIVED = "archived"
    STATUS_RESTORED = "restored"
    STATUS_CHOICES = [
        (STATUS_ARCHIVED, "Archivee"),
        (STATUS_RESTORED, "Restauree"),
    ]

    archive_type = models.CharField(max_length=20, choices=TYPE_CHOICES, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ARCHIVED, db_index=True)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="archive_batches", db_index=True)
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="archive_batches",
        db_index=True,
    )
    academic_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="archive_batches",
    )
    reason = models.TextField()
    snapshot = models.JSONField(default=dict, blank=True)
    classes_count = models.PositiveIntegerField(default=0)
    enrollments_count = models.PositiveIntegerField(default=0)
    inscriptions_count = models.PositiveIntegerField(default=0)
    students_count = models.PositiveIntegerField(default=0)
    grades_count = models.PositiveIntegerField(default=0)
    payments_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_archive_batches",
    )
    restored_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="restored_archive_batches",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    restored_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Lot d'archivage"
        verbose_name_plural = "Lots d'archivage"
        indexes = [
            models.Index(fields=["branch", "status", "created_at"], name="portal_arch_branch__a07eb8_idx"),
            models.Index(fields=["academic_year", "status"], name="portal_arch_academi_0f41bc_idx"),
            models.Index(fields=["archive_type", "status"], name="portal_arch_archive_735844_idx"),
        ]

    def __str__(self):
        class_label = f" - {self.academic_class}" if self.academic_class_id else ""
        return f"{self.get_archive_type_display()} {self.academic_year}{class_label}"


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


class TeacherDashboardPreference(models.Model):
    DEFAULT_OVERVIEW = "overview"
    DEFAULT_CLASSES = "classes"
    DEFAULT_SUPPORTS = "supports"
    DEFAULT_SCHEDULE = "schedule"
    DEFAULT_LOGS = "logs"
    DEFAULT_SETTINGS = "settings"

    DEFAULT_SECTION_CHOICES = [
        (DEFAULT_OVERVIEW, "Accueil"),
        (DEFAULT_CLASSES, "Mes classes"),
        (DEFAULT_SUPPORTS, "Supports"),
        (DEFAULT_SCHEDULE, "Planning"),
        (DEFAULT_LOGS, "Cahier de texte"),
        (DEFAULT_SETTINGS, "Parametres"),
    ]

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="teacher_dashboard_preferences",
        db_index=True,
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="teacher_dashboard_preferences",
        db_index=True,
    )
    dark_mode = models.BooleanField(default=False)
    sidebar_collapsed = models.BooleanField(default=False)
    compact_mode = models.BooleanField(default=False)
    default_section = models.CharField(
        max_length=20,
        choices=DEFAULT_SECTION_CHOICES,
        default=DEFAULT_OVERVIEW,
        db_index=True,
    )
    notify_lesson_reminders = models.BooleanField(default=True)
    notify_schedule_changes = models.BooleanField(default=True)
    notify_support_messages = models.BooleanField(default=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_teacher_dashboard_preferences",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Parametres dashboard enseignant"
        verbose_name_plural = "Parametres dashboard enseignants"
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "teacher"],
                name="portal_unique_teacher_dashboard_preference",
            )
        ]
        indexes = [
            models.Index(fields=["branch", "teacher"]),
            models.Index(fields=["teacher", "default_section"]),
        ]

    def __str__(self):
        return f"Parametres enseignant - {self.teacher}"


class DirectorTeacherAssignment(models.Model):
    SCOPE_CLASS = "class"
    SCOPE_SEMESTER = "semester"
    SCOPE_UE = "ue"
    SCOPE_EC = "ec"
    SCOPE_CHOICES = [
        (SCOPE_CLASS, "Classe"),
        (SCOPE_SEMESTER, "Semestre"),
        (SCOPE_UE, "UE"),
        (SCOPE_EC, "EC"),
    ]

    STATUS_ACTIVE = "active"
    STATUS_SUSPENDED = "suspended"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_SUSPENDED, "Suspendue"),
        (STATUS_ARCHIVED, "Archivee"),
    ]

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="director_teacher_assignments",
        db_index=True,
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="director_teacher_assignments",
        db_index=True,
    )
    scope_type = models.CharField(max_length=20, choices=SCOPE_CHOICES, default=SCOPE_CLASS, db_index=True)
    academic_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.CASCADE,
        related_name="director_teacher_assignments",
        null=True,
        blank=True,
    )
    semester = models.ForeignKey(
        Semester,
        on_delete=models.CASCADE,
        related_name="director_teacher_assignments",
        null=True,
        blank=True,
    )
    ue = models.ForeignKey(
        UE,
        on_delete=models.CASCADE,
        related_name="director_teacher_assignments",
        null=True,
        blank=True,
    )
    ec = models.ForeignKey(
        EC,
        on_delete=models.CASCADE,
        related_name="director_teacher_assignments",
        null=True,
        blank=True,
    )
    room_label = models.CharField(max_length=120, blank=True)
    planned_hours = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    starts_on = models.DateField(null=True, blank=True, db_index=True)
    ends_on = models.DateField(null=True, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_director_teacher_assignments",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_director_teacher_assignments",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    suspended_at = models.DateTimeField(null=True, blank=True, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["teacher__last_name", "teacher__first_name", "id"]
        verbose_name = "Affectation enseignant direction"
        verbose_name_plural = "Affectations enseignants direction"
        constraints = [
            models.UniqueConstraint(
                fields=["teacher", "scope_type", "academic_class", "semester", "ue", "ec", "starts_on", "ends_on"],
                name="portal_unique_director_teacher_assignment",
            )
        ]
        indexes = [
            models.Index(fields=["branch", "teacher"]),
            models.Index(fields=["branch", "academic_class"]),
            models.Index(fields=["branch", "ec"]),
        ]

    def __str__(self):
        class_label = self.academic_class.display_name if self.academic_class_id else "Sans classe"
        semester_label = f"S{self.semester.number}" if self.semester_id else ""
        ue_label = self.ue.code if self.ue_id else ""
        ec_label = self.ec.title if self.ec_id else "Sans matiere"
        room_label = self.room_label or "Salle non precisee"
        hours_label = f"{self.planned_hours} h prevues" if self.planned_hours is not None else "Volume non precise"
        scope_bits = " / ".join(bit for bit in [class_label, semester_label, ue_label, ec_label] if bit)
        return f"{self.teacher} - {scope_bits or 'Affectation'} - {room_label} - {hours_label}"

    def clean(self):
        errors = {}
        if self.planned_hours is not None and self.planned_hours <= 0:
            errors["planned_hours"] = "Le volume horaire doit etre superieur a 0."
        if self.status == self.STATUS_ARCHIVED and not self.archived_at:
            errors["archived_at"] = "La date d'archivage est obligatoire pour une affectation archivee."
        if self.status == self.STATUS_SUSPENDED and not self.suspended_at:
            errors["suspended_at"] = "La date de suspension est obligatoire pour une affectation suspendue."
        if self.starts_on and self.ends_on and self.starts_on > self.ends_on:
            errors["ends_on"] = "La date de fin doit etre posterieure a la date de debut."
        if self.scope_type == self.SCOPE_CLASS:
            if self.academic_class_id is None:
                errors["academic_class"] = "La classe est obligatoire."
        elif self.scope_type == self.SCOPE_SEMESTER:
            if self.semester_id is None:
                errors["semester"] = "Le semestre est obligatoire."
            elif self.academic_class_id and self.semester.academic_class_id != self.academic_class_id:
                errors["semester"] = "Le semestre selectionne n'appartient pas a la classe choisie."
        elif self.scope_type == self.SCOPE_UE:
            if self.ue_id is None:
                errors["ue"] = "L'UE est obligatoire."
            elif self.semester_id and self.ue.semester_id != self.semester_id:
                errors["ue"] = "L'UE selectionnee n'appartient pas au semestre choisi."
        elif self.scope_type == self.SCOPE_EC:
            if self.ec_id is None:
                errors["ec"] = "L'EC est obligatoire."
            elif self.ue_id and self.ec.ue_id != self.ue_id:
                errors["ec"] = "L'EC selectionnee n'appartient pas a l'UE choisie."
        else:
            errors["scope_type"] = "La portee selectionnee est invalide."

        if self.academic_class_id and self.ec_id and self.ec.ue.semester.academic_class_id != self.academic_class_id:
            errors["ec"] = "La matiere selectionnee n'appartient pas a la classe choisie."
        if self.ue_id and self.academic_class_id and self.ue.semester.academic_class_id != self.academic_class_id:
            errors["ue"] = "L'UE selectionnee n'appartient pas a la classe choisie."
        if self.academic_class_id and not self.room_label.strip():
            errors["room_label"] = "La salle de reference est obligatoire pour une affectation de classe."
        if self.academic_class_id and self.planned_hours is None:
            errors["planned_hours"] = "Le volume horaire prevu est obligatoire pour une affectation de classe."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.status == self.STATUS_ACTIVE:
            self.is_active = True
            self.suspended_at = None
            self.archived_at = None
        elif self.status == self.STATUS_SUSPENDED:
            self.is_active = False
            if not self.suspended_at:
                self.suspended_at = timezone.now()
            self.archived_at = None
        elif self.status == self.STATUS_ARCHIVED:
            self.is_active = False
            if not self.archived_at:
                self.archived_at = timezone.now()
        self.full_clean()
        return super().save(*args, **kwargs)


class TeacherDocument(models.Model):
    DOCUMENT_ID = "id"
    DOCUMENT_DIPLOMA = "diploma"
    DOCUMENT_CV = "cv"
    DOCUMENT_CONTRACT = "contract"
    DOCUMENT_OTHER = "other"
    DOCUMENT_CHOICES = [
        (DOCUMENT_ID, "Piece d'identite"),
        (DOCUMENT_DIPLOMA, "Diplome"),
        (DOCUMENT_CV, "CV"),
        (DOCUMENT_CONTRACT, "Contrat"),
        (DOCUMENT_OTHER, "Autre"),
    ]

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="teacher_documents",
        db_index=True,
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="teacher_documents",
        db_index=True,
    )
    document_type = models.CharField(max_length=30, choices=DOCUMENT_CHOICES, default=DOCUMENT_OTHER, db_index=True)
    file = models.FileField(upload_to=teacher_document_upload_path)
    note = models.CharField(max_length=255, blank=True)
    is_verified = models.BooleanField(default=False, db_index=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_teacher_documents",
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_teacher_documents",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Document enseignant"
        verbose_name_plural = "Documents enseignants"
        indexes = [
            models.Index(fields=["branch", "teacher"]),
            models.Index(fields=["branch", "document_type"]),
        ]

    def __str__(self):
        return f"{self.teacher} - {self.get_document_type_display()}"


def transfer_attachment_upload_path(instance, filename):
    branch_id = instance.branch_id or "unknown"
    return f"portal/transfers/{branch_id}/{filename}"


class TransferRequest(models.Model):
    TYPE_INTERNAL = "internal"
    TYPE_OUTGOING = "outgoing"
    TYPE_INCOMING = "incoming"
    TYPE_CLASS = TYPE_INTERNAL
    TYPE_SCHOOL = TYPE_OUTGOING
    TYPE_CHOICES = [
        (TYPE_INTERNAL, "Transfert interne"),
        (TYPE_OUTGOING, "Départ vers une autre école"),
        (TYPE_INCOMING, "Arrivée depuis une autre école"),
    ]

    STATUS_DRAFT = "draft"
    STATUS_SUBMITTED = "submitted"
    STATUS_UNDER_REVIEW = "under_review"
    STATUS_AWAITING_DOCUMENTS = "awaiting_documents"
    STATUS_APPROVED = "approved"
    STATUS_HANDOVER = "handover"
    STATUS_COMPLETED = "completed"
    STATUS_VALIDATED = STATUS_COMPLETED
    STATUS_REJECTED = "rejected"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Brouillon"),
        (STATUS_SUBMITTED, "Soumis"),
        (STATUS_UNDER_REVIEW, "En étude"),
        (STATUS_AWAITING_DOCUMENTS, "Pièces à compléter"),
        (STATUS_APPROVED, "Approuvé"),
        (STATUS_HANDOVER, "Remise en cours"),
        (STATUS_COMPLETED, "Terminé"),
        (STATUS_REJECTED, "Rejeté"),
        (STATUS_CANCELLED, "Annulé"),
    ]

    reference = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="transfer_requests",
        db_index=True,
    )
    enrollment = models.ForeignKey(
        "academics.AcademicEnrollment",
        on_delete=models.PROTECT,
        related_name="transfer_requests",
        null=True,
        blank=True,
    )
    transfer_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_CLASS, db_index=True)
    source_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.PROTECT,
        related_name="outgoing_transfer_requests",
        null=True,
        blank=True,
    )
    target_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.PROTECT,
        related_name="incoming_transfer_requests",
        null=True,
        blank=True,
    )
    target_school_name = models.CharField(max_length=180, blank=True)
    reason = models.TextField(blank=True)
    attachment = models.FileField(upload_to=transfer_attachment_upload_path, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SUBMITTED, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_transfer_requests",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_transfer_requests",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_transfer_requests",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True)
    source_snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Demande de transfert"
        verbose_name_plural = "Demandes de transfert"
        indexes = [
            models.Index(fields=["branch", "status"]),
            models.Index(fields=["branch", "transfer_type"]),
        ]

    def __str__(self):
        subject = self.enrollment or getattr(self, "incoming_details", None) or self.reference
        return f"{self.get_transfer_type_display()} - {subject}"


class TransferSchool(models.Model):
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="transfer_schools",
        db_index=True,
    )
    name = models.CharField(max_length=180)
    registration_number = models.CharField(max_length=80, blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    country = models.CharField(max_length=100, default="Mali")
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    is_partner = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_transfer_schools",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "city"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "name", "city"],
                name="portal_unique_transfer_school_branch_name_city",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.city})" if self.city else self.name


class InternalTransfer(models.Model):
    transfer_request = models.OneToOneField(
        TransferRequest,
        on_delete=models.CASCADE,
        related_name="internal_details",
    )
    target_programme = models.ForeignKey(
        "formations.Programme",
        on_delete=models.PROTECT,
        related_name="internal_transfer_destinations",
    )
    target_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.PROTECT,
        related_name="internal_transfer_placements",
    )
    source_level = models.CharField(max_length=20)
    target_level = models.CharField(max_length=20)
    academic_decision_reference = models.CharField(max_length=120, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.transfer_request.reference} -> {self.target_class}"


class OutgoingTransfer(models.Model):
    transfer_request = models.OneToOneField(
        TransferRequest,
        on_delete=models.CASCADE,
        related_name="outgoing_details",
    )
    destination_school = models.ForeignKey(
        TransferSchool,
        on_delete=models.PROTECT,
        related_name="incoming_student_files",
    )
    destination_programme = models.CharField(max_length=180, blank=True)
    destination_level = models.CharField(max_length=40, blank=True)
    academic_check_completed = models.BooleanField(default=False)
    administrative_check_completed = models.BooleanField(default=False)
    financial_check_completed = models.BooleanField(default=False)
    handover_at = models.DateTimeField(null=True, blank=True)

    @property
    def checks_completed(self):
        return all((
            self.academic_check_completed,
            self.administrative_check_completed,
            self.financial_check_completed,
        ))


class IncomingTransfer(models.Model):
    transfer_request = models.OneToOneField(
        TransferRequest,
        on_delete=models.CASCADE,
        related_name="incoming_details",
    )
    origin_school = models.ForeignKey(
        TransferSchool,
        on_delete=models.PROTECT,
        related_name="outgoing_student_files",
    )
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    birth_date = models.DateField()
    birth_place = models.CharField(max_length=150)
    gender = models.CharField(max_length=10, choices=(("male", "Masculin"), ("female", "Féminin")))
    phone = models.CharField(max_length=30)
    email = models.EmailField()
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default="Mali")
    requested_programme = models.ForeignKey(
        "formations.Programme",
        on_delete=models.PROTECT,
        related_name="incoming_transfer_requests",
    )
    requested_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.PROTECT,
        related_name="incoming_transfer_candidates",
        null=True,
        blank=True,
    )
    requested_level = models.CharField(max_length=20)
    equivalence_notes = models.TextField(blank=True)
    candidature = models.OneToOneField(
        "admissions.Candidature",
        on_delete=models.SET_NULL,
        related_name="incoming_transfer",
        null=True,
        blank=True,
    )

    def __str__(self):
        return f"{self.last_name} {self.first_name} - {self.origin_school}"


def transfer_document_upload_path(instance, filename):
    return f"portal/transfers/{instance.transfer_request.branch_id}/documents/{filename}"


class TransferDocument(models.Model):
    TYPE_REQUEST = "request"
    TYPE_TRANSCRIPT = "transcript"
    TYPE_CLEARANCE = "clearance"
    TYPE_IDENTITY = "identity"
    TYPE_EQUIVALENCE = "equivalence"
    TYPE_OTHER = "other"
    TYPE_CHOICES = [
        (TYPE_REQUEST, "Demande de transfert"),
        (TYPE_TRANSCRIPT, "Relevé de notes"),
        (TYPE_CLEARANCE, "Quitus administratif ou financier"),
        (TYPE_IDENTITY, "Pièce d'identité"),
        (TYPE_EQUIVALENCE, "Décision d'équivalence"),
        (TYPE_OTHER, "Autre document"),
    ]
    STATUS_PENDING = "pending"
    STATUS_VERIFIED = "verified"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_PENDING, "À vérifier"),
        (STATUS_VERIFIED, "Vérifié"),
        (STATUS_REJECTED, "Rejeté"),
    ]

    transfer_request = models.ForeignKey(
        TransferRequest,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    document_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default=TYPE_REQUEST)
    title = models.CharField(max_length=180)
    file = models.FileField(upload_to=transfer_document_upload_path)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="uploaded_transfer_documents",
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_transfer_documents",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class TransferDecision(models.Model):
    OUTCOME_APPROVED = "approved"
    OUTCOME_REJECTED = "rejected"
    OUTCOME_CHOICES = [
        (OUTCOME_APPROVED, "Approuvé"),
        (OUTCOME_REJECTED, "Rejeté"),
    ]
    transfer_request = models.OneToOneField(
        TransferRequest,
        on_delete=models.CASCADE,
        related_name="decision",
    )
    outcome = models.CharField(max_length=20, choices=OUTCOME_CHOICES)
    note = models.TextField(blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="transfer_decisions",
    )
    decided_at = models.DateTimeField(default=timezone.now)


class TransferHistory(models.Model):
    transfer_request = models.ForeignKey(
        TransferRequest,
        on_delete=models.CASCADE,
        related_name="history",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transfer_history_entries",
    )
    action = models.CharField(max_length=80, db_index=True)
    from_status = models.CharField(max_length=30, blank=True)
    to_status = models.CharField(max_length=30, blank=True)
    note = models.TextField(blank=True)
    snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["transfer_request", "created_at"])]


class AdministrativeDocument(models.Model):
    TYPE_NOTE_SERVICE = "note_service"
    TYPE_AVIS = "avis"
    TYPE_LETTRE = "lettre"
    TYPE_CONVOCATION = "convocation"
    TYPE_FICHE_TRANSFERT = "fiche_transfert"
    TYPE_FICHE_FREQUENTATION = "fiche_frequentation"

    TYPE_CHOICES = [
        (TYPE_NOTE_SERVICE, "Note de service"),
        (TYPE_AVIS, "Avis"),
        (TYPE_LETTRE, "Lettre"),
        (TYPE_CONVOCATION, "Convocation"),
        (TYPE_FICHE_TRANSFERT, "Fiche de transfert"),
        (TYPE_FICHE_FREQUENTATION, "Fiche de frequentation"),
    ]

    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Brouillon"),
        (STATUS_PUBLISHED, "Publie"),
    ]

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="admin_documents",
        db_index=True,
    )
    doc_type = models.CharField(max_length=30, choices=TYPE_CHOICES, db_index=True)
    title = models.CharField(max_length=200)
    reference = models.CharField(max_length=100, blank=True)
    body = models.TextField()
    recipients = models.TextField(blank=True, help_text="Destinataires (libre)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admin_documents_created",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Document administratif"
        verbose_name_plural = "Documents administratifs"
        indexes = [
            models.Index(fields=["branch", "doc_type"]),
            models.Index(fields=["branch", "status"]),
        ]

    def __str__(self):
        return f"{self.get_doc_type_display()} - {self.title}"
