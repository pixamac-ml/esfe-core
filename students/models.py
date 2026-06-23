# students/models.py

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from branches.models import Branch
from inscriptions.models import Inscription

User = get_user_model()


class GroupeSanguin(models.TextChoices):
    A_PLUS = "A+", "A+"
    A_MOINS = "A-", "A−"
    B_PLUS = "B+", "B+"
    B_MOINS = "B-", "B−"
    AB_PLUS = "AB+", "AB+"
    AB_MOINS = "AB-", "AB−"
    O_PLUS = "O+", "O+"
    O_MOINS = "O-", "O−"


class Student(models.Model):
    """
    Étudiant officiel de l’établissement.

    Créé automatiquement après le premier paiement validé.
    L'étudiant est lié à une inscription unique.
    """

    # =====================================================
    # RELATIONS
    # =====================================================

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="student_profile",
        db_index=True
    )

    inscription = models.OneToOneField(
        Inscription,
        on_delete=models.PROTECT,
        related_name="student",
        db_index=True
    )

    current_academic_enrollment = models.ForeignKey(
        "academics.AcademicEnrollment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_students",
        help_text="Inscription academique courante. L'ancien lien inscription reste conserve pour compatibilite.",
    )

    # =====================================================
    # IDENTITÉ ACADÉMIQUE
    # =====================================================

    matricule = models.CharField(
        max_length=30,
        unique=True,
        db_index=True
    )

    # =====================================================
    # DONNÉES CARTE
    # =====================================================

    photo = models.ImageField(
        upload_to="students/photos/",
        blank=True,
        help_text="Photo d’identité pour la carte étudiant"
    )

    groupe_sanguin = models.CharField(
        max_length=3,
        choices=GroupeSanguin.choices,
        blank=True,
        default="",
        help_text="Groupe sanguin déclaré (non vérifié médicalement)"
    )

    pin_hash = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Code PIN haché pour l’authentification par carte"
    )

    # =====================================================
    # STATUT
    # =====================================================

    is_active = models.BooleanField(
        default=True,
        help_text="Étudiant actif dans l’établissement"
    )

    # =====================================================
    # MÉTADONNÉES
    # =====================================================

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:

        ordering = ["-created_at"]

        indexes = [
            models.Index(fields=["matricule"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["created_at"]),
        ]

    # =====================================================
    # VALIDATION MÉTIER
    # =====================================================

    def clean(self):

        if not self.inscription:
            raise ValidationError("Une inscription est requise.")

        if not self.user:
            raise ValidationError("Un utilisateur est requis.")

        if self.inscription.status not in {"partial_paid", "active"}:
            raise ValidationError(
                "Impossible de créer un étudiant si l'inscription n'a pas encore de paiement validé."
            )

    # =====================================================
    # REPRÉSENTATION
    # =====================================================

    def __str__(self):

        try:
            c = self.inscription.candidature
            return f"{c.last_name} {c.first_name} ({self.matricule})"
        except Exception:
            return f"Student {self.matricule}"

    # =====================================================
    # ACCÈS RAPIDE AUX DONNÉES
    # =====================================================

    @property
    def full_name(self):

        c = self.inscription.candidature
        return f"{c.first_name} {c.last_name}"

    @property
    def email(self):

        return self.inscription.candidature.email

    @property
    def programme(self):

        return self.inscription.candidature.programme

    # =====================================================
    # PROPRIÉTÉS ACADÉMIQUES
    # =====================================================

    @property
    def programme_title(self):

        return self.programme.title

    @property
    def is_enrolled(self):

        return self.is_active and self.inscription.status == "active"

    # =====================================================
    # UTILITAIRES
    # =====================================================

    def deactivate(self):

        self.is_active = False
        self.save(update_fields=["is_active"])

    def reactivate(self):

        self.is_active = True
        self.save(update_fields=["is_active"])

    def set_pin(self, raw_pin: str) -> None:
        self.pin_hash = make_password(raw_pin)
        self.save(update_fields=["pin_hash"])

    def check_pin(self, raw_pin: str) -> bool:
        if not self.pin_hash:
            return False
        return check_password(raw_pin, self.pin_hash)

    @property
    def has_pin(self) -> bool:
        return bool(self.pin_hash)

    @property
    def carte_active(self):
        return self.cartes.filter(statut="active").order_by("-date_emission").first()


class StudentYearDecision(models.Model):
    DECISION_PROMOTED = "promoted"
    DECISION_PROMOTED_WITH_DEBT = "promoted_with_debt"
    DECISION_REPEATED = "repeated"
    DECISION_TRANSFERRED = "transferred"
    DECISION_SUSPENDED = "suspended"
    DECISION_ABANDONED = "abandoned"
    DECISION_COMPLETED = "completed"

    DECISION_CHOICES = [
        (DECISION_PROMOTED, "Passage"),
        (DECISION_PROMOTED_WITH_DEBT, "Passage avec dette"),
        (DECISION_REPEATED, "Redoublement"),
        (DECISION_TRANSFERRED, "Transfert"),
        (DECISION_SUSPENDED, "Suspension"),
        (DECISION_ABANDONED, "Abandon"),
        (DECISION_COMPLETED, "Cycle termine"),
    ]

    WORKFLOW_DRAFT = "draft"
    WORKFLOW_ACADEMIC_VALIDATED = "academic_validated"
    WORKFLOW_FINANCE_VALIDATED = "finance_validated"
    WORKFLOW_APPLIED = "applied"
    WORKFLOW_REJECTED = "rejected"

    WORKFLOW_STATUS_CHOICES = [
        (WORKFLOW_DRAFT, "Brouillon"),
        (WORKFLOW_ACADEMIC_VALIDATED, "Validee pedagogiquement"),
        (WORKFLOW_FINANCE_VALIDATED, "Validee finance"),
        (WORKFLOW_APPLIED, "Appliquee"),
        (WORKFLOW_REJECTED, "Rejetee"),
    ]

    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="year_decisions",
    )
    source_enrollment = models.ForeignKey(
        "academics.AcademicEnrollment",
        on_delete=models.PROTECT,
        related_name="year_decisions",
    )
    source_academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.PROTECT,
        related_name="student_year_decisions_as_source",
    )
    source_class = models.ForeignKey(
        "academics.AcademicClass",
        on_delete=models.PROTECT,
        related_name="student_year_decisions_as_source",
    )
    target_academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.PROTECT,
        related_name="student_year_decisions_as_target",
        null=True,
        blank=True,
    )
    target_class = models.ForeignKey(
        "academics.AcademicClass",
        on_delete=models.PROTECT,
        related_name="student_year_decisions_as_target",
        null=True,
        blank=True,
    )
    decision = models.CharField(max_length=20, choices=DECISION_CHOICES, db_index=True)
    workflow_status = models.CharField(
        max_length=30,
        choices=WORKFLOW_STATUS_CHOICES,
        default=WORKFLOW_DRAFT,
        db_index=True,
    )
    annual_average = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    decision_payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Trace de la regle academique automatique utilisee pour proposer la decision.",
    )
    note = models.TextField(blank=True)
    proposed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="proposed_student_year_decisions",
    )
    academic_validated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="academic_validated_student_year_decisions",
    )
    academic_validated_at = models.DateTimeField(null=True, blank=True)
    finance_validated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="finance_validated_student_year_decisions",
    )
    finance_validated_at = models.DateTimeField(null=True, blank=True)
    applied_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="applied_student_year_decisions",
    )
    applied_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rejected_student_year_decisions",
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    target_inscription = models.OneToOneField(
        "inscriptions.Inscription",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_year_decision",
    )
    target_enrollment = models.OneToOneField(
        "academics.AcademicEnrollment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_year_decision",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Decision annuelle etudiant"
        verbose_name_plural = "Decisions annuelles etudiants"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "source_enrollment"],
                name="students_unique_year_decision_per_enrollment",
            )
        ]
        indexes = [
            models.Index(fields=["source_academic_year", "decision"]),
            models.Index(fields=["source_class", "decision"]),
            models.Index(fields=["target_academic_year", "decision"]),
            models.Index(fields=["workflow_status", "created_at"]),
        ]

    def __str__(self):
        return f"{self.student} - {self.source_academic_year} - {self.get_decision_display()}"

    @property
    def can_academic_validate(self):
        return self.workflow_status == self.WORKFLOW_DRAFT

    @property
    def can_finance_validate(self):
        return self.workflow_status == self.WORKFLOW_ACADEMIC_VALIDATED

    @property
    def can_apply(self):
        return self.workflow_status == self.WORKFLOW_FINANCE_VALIDATED

    @property
    def can_reject(self):
        return self.workflow_status not in {self.WORKFLOW_APPLIED, self.WORKFLOW_REJECTED}

    def clean(self):
        errors = {}

        if self.source_enrollment_id and self.student_id:
            if self.source_enrollment.student_id != self.student.user_id:
                errors["source_enrollment"] = "L'inscription academique source ne correspond pas a l'etudiant."

        if self.source_enrollment_id and self.source_class_id:
            if self.source_enrollment.academic_class_id != self.source_class_id:
                errors["source_class"] = "La classe source ne correspond pas a l'inscription academique."

        if self.source_enrollment_id and self.source_academic_year_id:
            if self.source_enrollment.academic_year_id != self.source_academic_year_id:
                errors["source_academic_year"] = "L'annee source ne correspond pas a l'inscription academique."

        if self.target_class_id:
            if not self.target_class.is_active or self.target_class.is_archived:
                errors["target_class"] = "La classe cible doit etre active et non archivee."
            if self.target_academic_year_id and self.target_class.academic_year_id != self.target_academic_year_id:
                errors["target_class"] = "La classe cible ne correspond pas a l'annee cible."
            if self.source_enrollment_id:
                if self.target_class.programme_id != self.source_enrollment.programme_id:
                    errors["target_class"] = "La classe cible doit rester dans le meme programme en phase 1."
                if self.target_class.branch_id != self.source_enrollment.branch_id:
                    errors["target_class"] = "La classe cible doit rester dans la meme annexe en phase 1."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.source_enrollment_id:
            self.source_academic_year = self.source_enrollment.academic_year
            self.source_class = self.source_enrollment.academic_class
        self.full_clean()
        super().save(*args, **kwargs)


class StudentAttendance(models.Model):
    STATUS_PRESENT = "present"
    STATUS_ABSENT = "absent"
    STATUS_LATE = "late"

    STATUS_CHOICES = [
        (STATUS_PRESENT, "Present"),
        (STATUS_ABSENT, "Absent"),
        (STATUS_LATE, "En retard"),
    ]

    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="attendances",
    )
    academic_class = models.ForeignKey(
        "academics.AcademicClass",
        on_delete=models.PROTECT,
        related_name="student_attendances",
    )
    schedule_event = models.ForeignKey(
        "academics.AcademicScheduleEvent",
        on_delete=models.PROTECT,
        related_name="student_attendances",
        null=True,
        blank=True,
    )
    date = models.DateField(db_index=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        db_index=True,
    )
    arrival_time = models.TimeField(null=True, blank=True)
    justification = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="recorded_student_attendances",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="student_attendances",
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-updated_at"]
        verbose_name = "Presence etudiant"
        verbose_name_plural = "Presences etudiants"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "schedule_event"],
                name="students_unique_attendance_student_schedule_event",
            )
        ]
        indexes = [
            models.Index(fields=["academic_class", "date"]),
            models.Index(fields=["branch", "date"]),
            models.Index(fields=["status", "date"]),
        ]

    def __str__(self):
        return f"{self.student} - {self.date} - {self.status}"

    def clean(self):
        errors = {}

        if self.student_id and self.branch_id:
            candidature = getattr(getattr(self.student, "inscription", None), "candidature", None)
            if candidature and candidature.branch_id != self.branch_id:
                errors["branch"] = "L'annexe ne correspond pas a l'etudiant."

        if self.academic_class_id and self.branch_id and self.academic_class.branch_id != self.branch_id:
            errors["academic_class"] = "La classe ne correspond pas a l'annexe."

        if self.schedule_event_id:
            if self.schedule_event.branch_id != self.branch_id:
                errors["schedule_event"] = "L'evenement planifie ne correspond pas a l'annexe."
            elif self.schedule_event.academic_class_id != self.academic_class_id:
                errors["schedule_event"] = "L'evenement planifie ne correspond pas a la classe."
            elif timezone.localtime(self.schedule_event.start_datetime).date() != self.date:
                errors["date"] = "La date doit correspondre a celle de l'evenement planifie."

        if self.student_id and self.academic_class_id:
            has_enrollment = self.student.user.academic_enrollments.filter(
                academic_class=self.academic_class,
                is_active=True,
            ).exists()
            if not has_enrollment:
                errors["academic_class"] = "L'etudiant n'est pas affecte a cette classe."

        if self.status != self.STATUS_LATE and self.arrival_time:
            errors["arrival_time"] = "L'heure d'arrivee n'est renseignee que pour un retard."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class TeacherAttendance(models.Model):
    STATUS_PRESENT = "present"
    STATUS_ABSENT = "absent"
    STATUS_LATE = "late"

    STATUS_CHOICES = [
        (STATUS_PRESENT, "Present"),
        (STATUS_ABSENT, "Absent"),
        (STATUS_LATE, "En retard"),
    ]

    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="teacher_attendances",
    )
    schedule_event = models.ForeignKey(
        "academics.AcademicScheduleEvent",
        on_delete=models.PROTECT,
        related_name="teacher_attendances",
        null=True,
        blank=True,
    )
    date = models.DateField(db_index=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        db_index=True,
    )
    arrival_time = models.TimeField(null=True, blank=True)
    justification = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="recorded_teacher_attendances",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="teacher_attendances",
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-updated_at"]
        verbose_name = "Presence enseignant"
        verbose_name_plural = "Presences enseignants"
        constraints = [
            models.UniqueConstraint(
                fields=["teacher", "schedule_event"],
                name="students_unique_attendance_teacher_schedule_event",
            )
        ]
        indexes = [
            models.Index(fields=["branch", "date"]),
            models.Index(fields=["teacher", "date"]),
            models.Index(fields=["status", "date"]),
        ]

    def __str__(self):
        return f"{self.teacher} - {self.date} - {self.status}"

    def clean(self):
        errors = {}

        if self.schedule_event_id:
            if self.schedule_event.branch_id != self.branch_id:
                errors["schedule_event"] = "L'evenement planifie ne correspond pas a l'annexe."
            elif self.schedule_event.teacher_id != self.teacher_id:
                errors["schedule_event"] = "L'evenement planifie ne correspond pas a l'enseignant."
            elif timezone.localtime(self.schedule_event.start_datetime).date() != self.date:
                errors["date"] = "La date doit correspondre a celle de l'evenement planifie."

        if self.status != self.STATUS_LATE and self.arrival_time:
            errors["arrival_time"] = "L'heure d'arrivee n'est renseignee que pour un retard."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class AttendanceRollSheet(models.Model):
    """
    Feuille d'appel journaliere par classe (workflow surveillant : brouillon / valide).
    La saisie detaillee reste dans StudentAttendance (par seance).
    """

    STATUS_DRAFT = "draft"
    STATUS_VALIDATED = "validated"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "En cours"),
        (STATUS_VALIDATED, "Valide"),
    ]

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="attendance_roll_sheets",
        db_index=True,
    )
    academic_class = models.ForeignKey(
        "academics.AcademicClass",
        on_delete=models.CASCADE,
        related_name="attendance_roll_sheets",
    )
    date = models.DateField(db_index=True)
    schedule_event = models.ForeignKey(
        "academics.AcademicScheduleEvent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendance_roll_sheets",
        help_text="Seance de reference pour la saisie groupee (optionnel).",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True,
    )
    validated_at = models.DateTimeField(null=True, blank=True)
    validated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="validated_attendance_roll_sheets",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_attendance_roll_sheets",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-updated_at"]
        verbose_name = "Feuille d'appel (classe / jour)"
        verbose_name_plural = "Feuilles d'appel (classe / jour)"
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "academic_class", "date"],
                name="students_unique_roll_sheet_branch_class_date",
            )
        ]
        indexes = [
            models.Index(fields=["branch", "date", "status"]),
        ]

    def __str__(self):
        return f"{self.academic_class_id} — {self.date} ({self.get_status_display()})"


class AttendanceAlert(models.Model):
    TYPE_ABSENCE_REPETITION = "absence_repetition"
    TYPE_LATE_REPETITION = "late_repetition"

    TYPE_CHOICES = [
        (TYPE_ABSENCE_REPETITION, "Absences repetitives"),
        (TYPE_LATE_REPETITION, "Retards repetitifs"),
    ]

    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="attendance_alerts",
    )
    alert_type = models.CharField(
        max_length=30,
        choices=TYPE_CHOICES,
        db_index=True,
    )
    count = models.PositiveIntegerField(default=0)
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="attendance_alerts",
        db_index=True,
    )
    triggered_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_resolved = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["-triggered_at"]
        verbose_name = "Alerte assiduite"
        verbose_name_plural = "Alertes assiduite"
        indexes = [
            models.Index(fields=["branch", "triggered_at"]),
            models.Index(fields=["student", "alert_type"]),
        ]

    def __str__(self):
        return f"{self.student} - {self.alert_type} ({self.count})"


class StudentCase(models.Model):
    """Cas de suivi surveillant général pour un étudiant."""

    TYPE_ABSENCE_REPETEE = "absence_repetee"
    TYPE_RETARD_FREQUENT = "retard_frequent"
    TYPE_ABSENCE_LONGUE = "absence_longue"
    TYPE_SIGNALEMENT_COMPORTEMENTAL = "signalement_comportemental"
    TYPE_CONVOCATION_ETUDIANT = "convocation_etudiant"
    TYPE_CONVOCATION_PARENT = "convocation_parent"
    TYPE_SUIVI_PEDAGOGIQUE = "suivi_pedagogique"
    TYPE_ABSENT_EVALUATION = "absent_evaluation"
    TYPE_ENSEIGNANT_ABSENT = "enseignant_absent"
    TYPE_SIGNALEMENTS_MULTIPLES = "signalements_multiples"

    TYPE_CHOICES = [
        (TYPE_ABSENCE_REPETEE, "Absences répétées"),
        (TYPE_RETARD_FREQUENT, "Retards fréquents"),
        (TYPE_ABSENCE_LONGUE, "Absence longue"),
        (TYPE_SIGNALEMENT_COMPORTEMENTAL, "Signalement comportemental"),
        (TYPE_CONVOCATION_ETUDIANT, "Convocation étudiant"),
        (TYPE_CONVOCATION_PARENT, "Convocation parent/tuteur"),
        (TYPE_SUIVI_PEDAGOGIQUE, "Suivi pédagogique"),
        (TYPE_ABSENT_EVALUATION, "Absent à une évaluation"),
        (TYPE_ENSEIGNANT_ABSENT, "Enseignant absent sur plusieurs cours"),
        (TYPE_SIGNALEMENTS_MULTIPLES, "Plusieurs signalements"),
    ]

    STATUS_NOUVEAU = "nouveau"
    STATUS_EN_COURS = "en_cours"
    STATUS_ATTENTE_PARENT = "attente_parent"
    STATUS_EN_OBSERVATION = "en_observation"
    STATUS_CONVOQUE = "convoque"
    STATUS_RESOLU = "resolu"
    STATUS_ESCALADE = "escalade"

    STATUS_CHOICES = [
        (STATUS_NOUVEAU, "Nouveau"),
        (STATUS_EN_COURS, "En cours"),
        (STATUS_ATTENTE_PARENT, "En attente parent"),
        (STATUS_EN_OBSERVATION, "En observation"),
        (STATUS_CONVOQUE, "Convoqué"),
        (STATUS_RESOLU, "Résolu"),
        (STATUS_ESCALADE, "Escaladé direction"),
    ]

    # Flux simplifié à 4 étapes utilisé par le dashboard Surveillant Général
    # (nouveau -> en_cours -> convoque -> resolu) ; les autres statuts restent
    # accessibles via leurs mécanismes propres (attente parent, escalade direction).
    SIMPLE_FLOW_STATUSES = [STATUS_NOUVEAU, STATUS_EN_COURS, STATUS_CONVOQUE, STATUS_RESOLU]

    PRIORITY_FAIBLE = "faible"
    PRIORITY_NORMALE = "normale"
    PRIORITY_URGENTE = "urgente"
    PRIORITY_CRITIQUE = "critique"

    PRIORITY_CHOICES = [
        (PRIORITY_FAIBLE, "Faible"),
        (PRIORITY_NORMALE, "Normale"),
        (PRIORITY_URGENTE, "Urgente"),
        (PRIORITY_CRITIQUE, "Critique"),
    ]

    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="cases",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="student_cases",
        db_index=True,
    )
    case_type = models.CharField(max_length=40, choices=TYPE_CHOICES, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_NOUVEAU,
        db_index=True,
    )
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default=PRIORITY_NORMALE,
        db_index=True,
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    opened_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="opened_student_cases",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Cas étudiant"
        verbose_name_plural = "Cas étudiants"
        indexes = [
            models.Index(fields=["branch", "status"]),
            models.Index(fields=["student", "status"]),
            models.Index(fields=["priority", "status"]),
        ]

    def __str__(self):
        return f"[{self.get_priority_display()}] {self.title} — {self.student}"

    @property
    def is_open(self):
        return self.status not in {self.STATUS_RESOLU, self.STATUS_ESCALADE}

    def resolve(self, user):
        from django.utils import timezone as tz
        self.status = self.STATUS_RESOLU
        self.resolved_at = tz.now()
        self.save(update_fields=["status", "resolved_at", "updated_at"])
        StudentCaseNote.objects.create(
            case=self,
            author=user,
            content="Cas marqué comme résolu.",
        )


class StudentCaseNote(models.Model):
    """Note interne sur un cas étudiant."""

    case = models.ForeignKey(
        StudentCase,
        on_delete=models.CASCADE,
        related_name="notes",
    )
    author = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="case_notes",
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Note de cas"
        verbose_name_plural = "Notes de cas"

    def __str__(self):
        return f"Note #{self.pk} — Cas #{self.case_id}"


class TeacherCase(models.Model):
    """Cas de suivi surveillant général pour un enseignant (miroir de StudentCase)."""

    TYPE_RETARD_REPETE = "retard_repete"
    TYPE_ABSENCE_NON_JUSTIFIEE = "absence_non_justifiee"
    TYPE_APPEL_NON_FAIT = "appel_non_fait"
    TYPE_MANQUEMENT_PEDAGOGIQUE = "manquement_pedagogique"
    TYPE_INCIDENT = "incident"
    TYPE_AUTRE = "autre"

    TYPE_CHOICES = [
        (TYPE_RETARD_REPETE, "Retards répétés"),
        (TYPE_ABSENCE_NON_JUSTIFIEE, "Absence non justifiée"),
        (TYPE_APPEL_NON_FAIT, "Appel non fait de façon récurrente"),
        (TYPE_MANQUEMENT_PEDAGOGIQUE, "Manquement pédagogique"),
        (TYPE_INCIDENT, "Incident signalé"),
        (TYPE_AUTRE, "Autre"),
    ]

    STATUS_NOUVEAU = StudentCase.STATUS_NOUVEAU
    STATUS_EN_COURS = StudentCase.STATUS_EN_COURS
    STATUS_CONVOQUE = StudentCase.STATUS_CONVOQUE
    STATUS_RESOLU = StudentCase.STATUS_RESOLU

    STATUS_CHOICES = [
        (STATUS_NOUVEAU, "Nouveau"),
        (STATUS_EN_COURS, "En cours"),
        (STATUS_CONVOQUE, "Convoqué"),
        (STATUS_RESOLU, "Résolu"),
    ]

    PRIORITY_FAIBLE = StudentCase.PRIORITY_FAIBLE
    PRIORITY_NORMALE = StudentCase.PRIORITY_NORMALE
    PRIORITY_URGENTE = StudentCase.PRIORITY_URGENTE
    PRIORITY_CRITIQUE = StudentCase.PRIORITY_CRITIQUE
    PRIORITY_CHOICES = StudentCase.PRIORITY_CHOICES

    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="teacher_cases",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="teacher_cases",
        db_index=True,
    )
    case_type = models.CharField(max_length=40, choices=TYPE_CHOICES, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_NOUVEAU,
        db_index=True,
    )
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default=PRIORITY_NORMALE,
        db_index=True,
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    opened_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="opened_teacher_cases",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Cas enseignant"
        verbose_name_plural = "Cas enseignants"
        indexes = [
            models.Index(fields=["branch", "status"]),
            models.Index(fields=["teacher", "status"]),
            models.Index(fields=["priority", "status"]),
        ]

    def __str__(self):
        return f"[{self.get_priority_display()}] {self.title} — {self.teacher}"

    @property
    def is_open(self):
        return self.status != self.STATUS_RESOLU

    def resolve(self, user):
        self.status = self.STATUS_RESOLU
        self.resolved_at = timezone.now()
        self.save(update_fields=["status", "resolved_at", "updated_at"])
        TeacherCaseNote.objects.create(
            case=self,
            author=user,
            content="Cas marqué comme résolu.",
        )


class TeacherCaseNote(models.Model):
    """Note interne sur un cas enseignant."""

    case = models.ForeignKey(
        TeacherCase,
        on_delete=models.CASCADE,
        related_name="notes",
    )
    author = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="teacher_case_notes",
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Note de cas enseignant"
        verbose_name_plural = "Notes de cas enseignant"

    def __str__(self):
        return f"Note #{self.pk} — Cas enseignant #{self.case_id}"


class Convocation(models.Model):
    """Convocation disciplinaire envoyée par le surveillant général (étudiant/parents ou enseignant)."""

    TARGET_STUDENT = "student"
    TARGET_TEACHER = "teacher"
    TARGET_CHOICES = [
        (TARGET_STUDENT, "Étudiant"),
        (TARGET_TEACHER, "Enseignant"),
    ]

    DEST_STUDENT = "etudiant"
    DEST_PARENTS = "parents"
    DEST_BOTH = "les_deux"
    DEST_CHOICES = [
        (DEST_STUDENT, "L'étudiant"),
        (DEST_PARENTS, "Les parents"),
        (DEST_BOTH, "Les deux"),
    ]

    CHANNEL_SMS = "sms"
    CHANNEL_CALL = "call"
    CHANNEL_EMAIL = "email"
    CHANNEL_LETTER = "letter"
    CHANNEL_CHOICES = [
        (CHANNEL_SMS, "SMS"),
        (CHANNEL_CALL, "Appel téléphonique"),
        (CHANNEL_EMAIL, "E-mail"),
        (CHANNEL_LETTER, "Courrier remis"),
    ]

    STATUS_PLANNED = "planned"
    STATUS_SENT = "sent"
    STATUS_MANUAL = "manual_pending"
    STATUS_CHOICES = [
        (STATUS_PLANNED, "Planifiée"),
        (STATUS_SENT, "Envoyée"),
        (STATUS_MANUAL, "À traiter manuellement"),
    ]

    target_type = models.CharField(max_length=10, choices=TARGET_CHOICES, db_index=True)
    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="convocations",
        null=True,
        blank=True,
    )
    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="convocations",
        null=True,
        blank=True,
    )
    student_case = models.ForeignKey(
        StudentCase,
        on_delete=models.SET_NULL,
        related_name="convocations",
        null=True,
        blank=True,
    )
    teacher_case = models.ForeignKey(
        TeacherCase,
        on_delete=models.SET_NULL,
        related_name="convocations",
        null=True,
        blank=True,
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="convocations",
        db_index=True,
    )
    destinataire = models.CharField(max_length=10, choices=DEST_CHOICES, blank=True)
    motif = models.CharField(max_length=200)
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES)
    scheduled_date = models.DateField()
    scheduled_time = models.TimeField()
    message = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PLANNED)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="created_convocations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Convocation"
        verbose_name_plural = "Convocations"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(target_type="student", student__isnull=False, teacher__isnull=True)
                    | models.Q(target_type="teacher", teacher__isnull=False, student__isnull=True)
                ),
                name="convocation_target_matches_fk",
            ),
        ]

    def __str__(self):
        target = self.student if self.target_type == self.TARGET_STUDENT else self.teacher
        return f"Convocation {self.get_channel_display()} — {target} ({self.scheduled_date})"


# =============================================================
# CARTE ÉTUDIANT
# =============================================================

class StatutCarte(models.TextChoices):
    ACTIVE = "active", "Active"
    REVOQUEE = "revoquee", "Révoquée"
    PERDUE = "perdue", "Perdue"
    EXPIREE = "expiree", "Expirée"


class CarteEtudiant(models.Model):
    """
    Carte d'identité estudiantine émise par l'établissement.
    La validité se vérifie : signature HMAC + statut active + date_expiration >= aujourd'hui.
    """

    etudiant = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="cartes",
    )
    annee = models.CharField(max_length=9, help_text="Année académique, ex: 2026-2027")
    code_annexe = models.CharField(max_length=20, help_text="Code annexe, ex: BKO-MORIBA")
    date_emission = models.DateField(auto_now_add=True)
    date_expiration = models.DateField()
    statut = models.CharField(
        max_length=10,
        choices=StatutCarte.choices,
        default=StatutCarte.ACTIVE,
        db_index=True,
    )
    token_version = models.CharField(max_length=4, default="v1")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_emission"]
        verbose_name = "Carte étudiant"
        verbose_name_plural = "Cartes étudiants"
        indexes = [
            models.Index(fields=["etudiant", "statut"]),
            models.Index(fields=["statut", "date_expiration"]),
        ]

    def __str__(self):
        return f"Carte {self.etudiant.matricule} — {self.annee} ({self.statut})"

    @property
    def is_valide(self) -> bool:
        return (
            self.statut == StatutCarte.ACTIVE
            and self.date_expiration >= timezone.localdate()
        )

    def revoquer(self, motif: str = "revoquee") -> None:
        if motif not in StatutCarte.values:
            motif = StatutCarte.REVOQUEE
        self.statut = motif
        self.save(update_fields=["statut"])


class VerificationLog(models.Model):
    """Journal des consultations du portail de vérification (RGPD + sécurité)."""

    carte = models.ForeignKey(
        CarteEtudiant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verifications",
    )
    code_tente = models.CharField(max_length=20, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    resultat = models.CharField(max_length=20, default="invalide")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Log de vérification carte"
        verbose_name_plural = "Logs de vérification carte"

