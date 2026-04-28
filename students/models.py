# students/models.py

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from branches.models import Branch
from inscriptions.models import Inscription

User = get_user_model()


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

    # =====================================================
    # IDENTITÉ ACADÉMIQUE
    # =====================================================

    matricule = models.CharField(
        max_length=30,
        unique=True,
        db_index=True
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
