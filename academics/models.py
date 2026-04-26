from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from branches.models import Branch
from formations.models import Programme
from inscriptions.models import Inscription

from academics.services.grading import apply_ec_grade
from academics.services.semester import compute_semester_result
from academics.services.ue import compute_ue_result


class AcademicYear(models.Model):
    """
    Référence centrale des années académiques.
    """

    name = models.CharField(
        max_length=9,
        unique=True,
        help_text="Format attendu : 2025-2026",
    )
    start_date = models.DateField(
        help_text="Date de début de l'année académique",
    )
    end_date = models.DateField(
        help_text="Date de fin de l'année académique",
    )
    is_active = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Une seule année académique doit être active à la fois.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]
        verbose_name = "Année académique"
        verbose_name_plural = "Années académiques"

    def __str__(self):
        return self.name

    def clean(self):
        errors = {}

        if self.start_date >= self.end_date:
            errors["end_date"] = "La date de fin doit être postérieure à la date de début."

        if self.is_active:
            qs = AcademicYear.objects.filter(is_active=True).exclude(pk=self.pk)
            if qs.exists():
                errors["is_active"] = "Une seule année académique peut être active."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class AcademicClass(models.Model):
    """
    Classe académique réelle.
    """

    STUDY_LEVEL_CHOICES = [
        ("DEF", "Diplôme d'Études Fondamentales"),
        ("BAC", "Baccalauréat"),
        ("LICENCE", "Licence"),
        ("MASTER", "Master"),
    ]

    name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Nom libre temporaire. Peut rester vide si l'affichage est reconstruit dynamiquement.",
    )

    programme = models.ForeignKey(
        Programme,
        on_delete=models.PROTECT,
        related_name="academic_classes",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="academic_classes",
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="academic_classes",
    )

    level = models.CharField(
        max_length=10,
        help_text="Exemples : L1, L2, L3, M1, M2...",
    )

    study_level = models.CharField(
        max_length=20,
        choices=STUDY_LEVEL_CHOICES,
        null=True,
        blank=True,
        help_text="Niveau d'études d'entrée ou de référence pour la logique métier.",
    )

    validation_threshold = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Seuil de validation de référence : 10 ou 12 selon le niveau.",
    )

    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["programme__title", "branch__name", "level"]
        verbose_name = "Classe académique"
        verbose_name_plural = "Classes académiques"
        constraints = [
            models.UniqueConstraint(
                fields=["programme", "branch", "academic_year", "level"],
                name="unique_academic_class_per_programme_branch_year_level",
            )
        ]

    def __str__(self):
        if self.name:
            return self.name
        return f"{self.level} {self.programme} - {self.branch}"

    @property
    def display_name(self):
        return str(self)

    def clean(self):
        errors = {}

        if self.validation_threshold is not None and self.validation_threshold <= 0:
            errors["validation_threshold"] = "Le seuil de validation doit être supérieur à 0."

        if self.validation_threshold is not None and self.validation_threshold > 20:
            errors["validation_threshold"] = "Le seuil de validation ne peut pas dépasser 20."

        if errors:
            raise ValidationError(errors)


class AcademicEnrollment(models.Model):
    """
    Pont entre l'inscription administrative et le système académique.
    """

    inscription = models.OneToOneField(
        Inscription,
        on_delete=models.CASCADE,
        related_name="academic_enrollment",
    )

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="academic_enrollments",
    )

    programme = models.ForeignKey(
        Programme,
        on_delete=models.PROTECT,
        related_name="academic_enrollments",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="academic_enrollments",
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="academic_enrollments",
    )
    academic_class = models.ForeignKey(
        "AcademicClass",
        on_delete=models.PROTECT,
        related_name="enrollments",
    )

    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Inscription académique"
        verbose_name_plural = "Inscriptions académiques"

    def __str__(self):
        return f"{self.student} - {self.programme} ({self.academic_year})"

    def clean(self):
        errors = {}

        validated_payment_exists = self.inscription.payments.filter(status="validated").exists()
        linked_student_exists = hasattr(self.inscription, "student")

        if not (
            self.inscription.status in {"partial_paid", "active"}
            or validated_payment_exists
            or linked_student_exists
        ):
            errors["inscription"] = (
                "L'inscription doit avoir au moins un paiement valide ou un etudiant cree "
                "pour permettre la creation d'une inscription academique."
            )

        candidature = self.inscription.candidature

        if self.programme_id and candidature and self.programme != candidature.programme:
            errors["programme"] = "Incohérence avec le programme de la candidature."

        if self.branch_id and candidature and self.branch != candidature.branch:
            errors["branch"] = "Incohérence avec l'annexe choisie."

        # Vérification temporairement désactivée car le site legacy stocke encore academic_year en string.
        # À remettre quand l'ancien workflow sera normalisé.
        # if self.academic_year_id and candidature:
        #     if str(self.academic_year.name) != str(candidature.academic_year):
        #         errors["academic_year"] = "Incohérence avec l'année académique."

        if self.academic_class_id:
            if self.academic_class.programme != self.programme:
                errors["academic_class"] = "La classe ne correspond pas au programme."

            if self.academic_class.branch != self.branch:
                errors["academic_class"] = "La classe ne correspond pas à l'annexe."

            if self.academic_class.academic_year != self.academic_year:
                errors["academic_class"] = "La classe ne correspond pas à l'année académique."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Semester(models.Model):
    """
    Semestre rattaché à une classe.
    """

    STATUS_DRAFT = "DRAFT"
    STATUS_NORMAL_ENTRY = "NORMAL_ENTRY"
    STATUS_NORMAL_LOCKED = "NORMAL_LOCKED"
    STATUS_RETAKE_ENTRY = "RETAKE_ENTRY"
    STATUS_FINALIZED = "FINALIZED"
    STATUS_PUBLISHED = "PUBLISHED"

    SEMESTER_CHOICES = [
        (1, "Semestre 1"),
        (2, "Semestre 2"),
    ]
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Brouillon"),
        (STATUS_NORMAL_ENTRY, "Saisie normale"),
        (STATUS_NORMAL_LOCKED, "Session normale terminee"),
        (STATUS_RETAKE_ENTRY, "Rattrapage"),
        (STATUS_FINALIZED, "Finalise"),
        (STATUS_PUBLISHED, "Publie"),
    ]

    academic_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.CASCADE,
        related_name="semesters",
    )

    number = models.IntegerField(choices=SEMESTER_CHOICES)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )

    total_required_credits = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("30.00"),
    )

    class Meta:
        ordering = ["academic_class", "number"]
        verbose_name = "Semestre"
        verbose_name_plural = "Semestres"
        constraints = [
            models.UniqueConstraint(
                fields=["academic_class", "number"],
                name="unique_semester_per_academic_class",
            )
        ]

    def __str__(self):
        return f"{self.academic_class} - S{self.number}"

    def clean(self):
        errors = {}

        if errors:
            raise ValidationError(errors)

    def calculate_for_enrollment(self, enrollment):
        return compute_semester_result(self, enrollment)


class UE(models.Model):
    """
    Unité d'enseignement.
    """

    semester = models.ForeignKey(
        Semester,
        on_delete=models.CASCADE,
        related_name="ues",
    )

    code = models.CharField(max_length=50)
    title = models.CharField(max_length=255)

    class Meta:
        ordering = ["semester", "code"]
        verbose_name = "UE"
        verbose_name_plural = "UE"
        constraints = [
            models.UniqueConstraint(
                fields=["semester", "code"],
                name="unique_ue_code_per_semester",
            )
        ]

    def __str__(self):
        return f"{self.code} - {self.title}"

    @property
    def credit_required(self):
        total = self.ecs.aggregate(total=models.Sum("credit_required"))["total"]
        return total or Decimal("0.00")

    @property
    def coefficient(self):
        total = self.ecs.aggregate(total=models.Sum("coefficient"))["total"]
        return total or Decimal("0.00")

    def clean(self):
        errors = {}

        # Crédit requis > 0
        if self.credit_required is not None and self.credit_required <= 0:
            errors["credit_required"] = "Le crédit requis doit être supérieur à 0."

        # Coefficient > 0
        if self.coefficient is not None and self.coefficient <= 0:
            errors["coefficient"] = "Le coefficient doit être supérieur à 0."

        # Crédit requis max 6
        if self.credit_required is not None and self.credit_required > Decimal("6.00"):
            errors["credit_required"] = "Une UE ne peut pas dépasser 6 crédits requis."

        # Cohérence crédit/coefficient
        if (
            self.credit_required is not None
            and self.coefficient is not None
            and self.credit_required > 0
            and self.coefficient > 0
            and self.credit_required < self.coefficient
        ):
            errors["credit_required"] = "Le crédit requis ne peut pas être inférieur au coefficient."

        if errors:
            raise ValidationError(errors)

    def calculate_for_enrollment(self, enrollment):
        return compute_ue_result(self, enrollment)


class EC(models.Model):
    """
    Élément constitutif (matière réelle).
    """

    ue = models.ForeignKey(
        UE,
        on_delete=models.CASCADE,
        related_name="ecs",
    )

    title = models.CharField(max_length=255)

    credit_required = models.DecimalField(max_digits=5, decimal_places=2)
    coefficient = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        ordering = ["ue", "id"]
        verbose_name = "EC"
        verbose_name_plural = "EC"

    def __str__(self):
        return f"{self.title} ({self.ue})"

    def clean(self):
        errors = {}

        # Crédit requis > 0
        if self.credit_required is not None and self.credit_required <= 0:
            errors["credit_required"] = "Le crédit requis doit être supérieur à 0."

        # Coefficient > 0
        if self.coefficient is not None and self.coefficient <= 0:
            errors["coefficient"] = "Le coefficient doit être supérieur à 0."

        # Crédit requis max 6
        if self.credit_required is not None and self.credit_required > Decimal("6.00"):
            errors["credit_required"] = "Le crédit requis d'un EC ne peut pas dépasser 6."

        # Cohérence crédit/coefficient
        if (
            self.credit_required is not None
            and self.coefficient is not None
            and self.credit_required > 0
            and self.coefficient > 0
            and self.credit_required < self.coefficient
        ):
            errors["credit_required"] = "Le crédit requis ne peut pas être inférieur au coefficient."

        if errors:
            raise ValidationError(errors)


class ECChapter(models.Model):
    ec = models.ForeignKey(
        "EC",
        on_delete=models.CASCADE,
        related_name="chapters",
    )
    title = models.CharField(max_length=255)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Chapitre EC"
        verbose_name_plural = "Chapitres EC"

    def __str__(self):
        return f"{self.ec.title} - {self.title}"


class ECContent(models.Model):
    CONTENT_TYPE_PDF = "pdf"
    CONTENT_TYPE_VIDEO = "video"
    CONTENT_TYPE_DOC = "doc"
    CONTENT_TYPE_EXCEL = "excel"
    CONTENT_TYPE_PPT = "ppt"
    CONTENT_TYPE_IMAGE = "image"
    CONTENT_TYPE_AUDIO = "audio"
    CONTENT_TYPE_TEXT = "text"
    CONTENT_TYPE_CHOICES = [
        (CONTENT_TYPE_PDF, "PDF"),
        (CONTENT_TYPE_VIDEO, "Vidéo"),
        (CONTENT_TYPE_DOC, "Word"),
        (CONTENT_TYPE_EXCEL, "Excel"),
        (CONTENT_TYPE_PPT, "PowerPoint"),
        (CONTENT_TYPE_IMAGE, "Image"),
        (CONTENT_TYPE_AUDIO, "Audio"),
        (CONTENT_TYPE_TEXT, "Texte"),
    ]

    chapter = models.ForeignKey(
        "ECChapter",
        on_delete=models.CASCADE,
        related_name="contents",
    )
    title = models.CharField(max_length=255)
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES)
    file = models.FileField(upload_to="courses/", null=True, blank=True)
    video_url = models.URLField(null=True, blank=True)
    text_content = models.TextField(blank=True)
    duration = models.PositiveIntegerField(null=True, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Contenu EC"
        verbose_name_plural = "Contenus EC"

    def __str__(self):
        return f"{self.title} - {self.chapter.title}"

    @property
    def ec(self):
        return self.chapter.ec

    def clean(self):
        errors = {}
        text_value = (self.text_content or "").strip()

        file_based_types = {
            self.CONTENT_TYPE_PDF,
            self.CONTENT_TYPE_DOC,
            self.CONTENT_TYPE_EXCEL,
            self.CONTENT_TYPE_PPT,
            self.CONTENT_TYPE_IMAGE,
            self.CONTENT_TYPE_AUDIO,
        }
        if self.content_type in file_based_types and not self.file:
            errors["file"] = "Un fichier est requis pour ce type de contenu."

        if self.content_type == self.CONTENT_TYPE_VIDEO and not self.video_url:
            errors["video_url"] = "Une URL vidéo est requise pour ce type de contenu."

        if self.content_type == self.CONTENT_TYPE_TEXT and not text_value:
            errors["text_content"] = "Un texte est requis pour ce type de contenu."

        if self.content_type != self.CONTENT_TYPE_VIDEO and self.video_url:
            errors["video_url"] = "L'URL vidéo ne doit être utilisée que pour un contenu vidéo."

        if self.content_type != self.CONTENT_TYPE_TEXT and text_value:
            errors["text_content"] = "Le texte direct n'est disponible que pour le type Texte."

        if self.content_type not in file_based_types and self.file:
            errors["file"] = "Le fichier n'est disponible que pour les contenus bases sur fichier."

        if self.duration is not None and self.duration <= 0:
            errors["duration"] = "La duree doit etre superieure a 0."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class StudentContentProgress(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="content_progresses",
    )
    content = models.ForeignKey(
        ECContent,
        on_delete=models.CASCADE,
        related_name="student_progresses",
    )
    is_completed = models.BooleanField(default=False)
    progress_percent = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    last_position = models.PositiveIntegerField(default=0)
    first_viewed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Progression contenu etudiant"
        verbose_name_plural = "Progressions contenus etudiants"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "content"],
                name="unique_student_content_progress",
            )
        ]

    def __str__(self):
        return f"{self.student} - {self.content} ({self.progress_percent}%)"

    def clean(self):
        if self.is_completed and self.progress_percent < 100:
            self.progress_percent = 100

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ECGrade(models.Model):
    """
    Note d'un étudiant sur un EC.

    IMPORTANT :
    - la note peut être vide temporairement
    - la saisie se fait progressivement
    - le calcul ne doit jamais casser si toutes les notes ne sont pas encore remplies
    """

    enrollment = models.ForeignKey(
        AcademicEnrollment,
        on_delete=models.CASCADE,
        related_name="ec_grades",
    )

    ec = models.ForeignKey(
        EC,
        on_delete=models.CASCADE,
        related_name="grades",
    )

    # Champ historique conservé pour compatibilité avec l'existant.
    note = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    normal_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    retake_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    final_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    note_coefficient = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
    )
    credit_obtained = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
    )
    is_validated = models.BooleanField(default=False)

    class Meta:
        ordering = ["enrollment", "ec"]
        verbose_name = "Note EC"
        verbose_name_plural = "Notes EC"
        constraints = [
            models.UniqueConstraint(
                fields=["enrollment", "ec"],
                name="unique_ec_grade_per_enrollment",
            )
        ]

    def __str__(self):
        return f"{self.enrollment} - {self.ec} : {self.final_score}"

    def clean(self):
        errors = {}

        score_to_validate = self.final_score if self.final_score is not None else self.note
        if score_to_validate is not None:
            try:
                note_val = float(score_to_validate)
                if note_val < 0 or note_val > 20:
                    errors["note"] = "La note doit être comprise entre 0 et 20."
            except Exception:
                errors["note"] = "Valeur de note invalide."

        if self.enrollment_id and self.ec_id:
            if self.enrollment.academic_class.programme != self.ec.ue.semester.academic_class.programme:
                errors["ec"] = "L'EC choisi n'appartient pas au bon programme."

            if self.enrollment.academic_class != self.ec.ue.semester.academic_class:
                errors["ec"] = "L'EC choisi n'appartient pas à la classe de cette inscription académique."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.normal_score is None and self.note is not None:
            self.normal_score = self.note

        self.full_clean()
        apply_ec_grade(self)
        super().save(*args, **kwargs)


class AcademicScheduleEvent(models.Model):
    EVENT_TYPE_COURSE = "course"
    EVENT_TYPE_EXAM = "exam"
    EVENT_TYPE_MEETING = "meeting"
    EVENT_TYPE_PRACTICAL = "practical"
    EVENT_TYPE_SEMINAR = "seminar"
    EVENT_TYPE_OTHER = "other"
    EVENT_TYPE_CHOICES = [
        (EVENT_TYPE_COURSE, "Cours"),
        (EVENT_TYPE_EXAM, "Examen"),
        (EVENT_TYPE_MEETING, "Reunion"),
        (EVENT_TYPE_PRACTICAL, "Travaux pratiques"),
        (EVENT_TYPE_SEMINAR, "Seminaire"),
        (EVENT_TYPE_OTHER, "Autre"),
    ]

    STATUS_DRAFT = "draft"
    STATUS_PLANNED = "planned"
    STATUS_ONGOING = "ongoing"
    STATUS_COMPLETED = "completed"
    STATUS_POSTPONED = "postponed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Brouillon"),
        (STATUS_PLANNED, "Planifie"),
        (STATUS_ONGOING, "En cours"),
        (STATUS_COMPLETED, "Termine"),
        (STATUS_POSTPONED, "Reporte"),
        (STATUS_CANCELLED, "Annule"),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES, default=EVENT_TYPE_COURSE, db_index=True)
    academic_class = models.ForeignKey("AcademicClass", on_delete=models.PROTECT, related_name="schedule_events")
    ec = models.ForeignKey("EC", on_delete=models.PROTECT, related_name="schedule_events")
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="teaching_schedule_events")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="schedule_events")
    academic_year = models.ForeignKey("AcademicYear", on_delete=models.PROTECT, related_name="schedule_events")
    start_datetime = models.DateTimeField(db_index=True)
    end_datetime = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    location = models.CharField(max_length=255, blank=True)
    is_online = models.BooleanField(default=False)
    meeting_link = models.URLField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_schedule_events")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="updated_schedule_events")
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_datetime", "id"]
        verbose_name = "Evenement academique"
        verbose_name_plural = "Evenements academiques"
        indexes = [
            models.Index(fields=["branch", "academic_year", "start_datetime"]),
            models.Index(fields=["academic_class", "start_datetime"]),
            models.Index(fields=["teacher", "start_datetime"]),
            models.Index(fields=["status", "start_datetime"]),
        ]

    def __str__(self):
        return f"{self.title} - {self.academic_class} ({self.start_datetime:%d/%m %H:%M})"

    @property
    def duration_minutes(self):
        return int((self.end_datetime - self.start_datetime).total_seconds() // 60)

    def clean(self):
        errors = {}

        if self.start_datetime and self.end_datetime and self.start_datetime >= self.end_datetime:
            errors["end_datetime"] = "La date de fin doit etre posterieure a la date de debut."

        if self.academic_class_id and self.branch_id and self.academic_class.branch_id != self.branch_id:
            errors["branch"] = "L'annexe ne correspond pas a la classe academique."

        if self.academic_class_id and self.academic_year_id and self.academic_class.academic_year_id != self.academic_year_id:
            errors["academic_year"] = "L'annee academique ne correspond pas a la classe academique."

        if self.ec_id and self.academic_class_id and self.ec.ue.semester.academic_class_id != self.academic_class_id:
            errors["ec"] = "L'EC ne correspond pas a la classe academique selectionnee."

        if self.is_online and not self.meeting_link:
            errors["meeting_link"] = "Le lien de reunion est obligatoire pour un evenement en ligne."

        if not self.is_online and self.meeting_link and not self.location:
            # allowed but encourage explicit destination
            pass

        if errors:
            raise ValidationError(errors)


class AcademicScheduleChangeLog(models.Model):
    ACTION_CREATED = "created"
    ACTION_UPDATED = "updated"
    ACTION_POSTPONED = "postponed"
    ACTION_CANCELLED = "cancelled"
    ACTION_COMPLETED = "completed"
    ACTION_CHOICES = [
        (ACTION_CREATED, "Cree"),
        (ACTION_UPDATED, "Mis a jour"),
        (ACTION_POSTPONED, "Reporte"),
        (ACTION_CANCELLED, "Annule"),
        (ACTION_COMPLETED, "Termine"),
    ]

    event = models.ForeignKey(AcademicScheduleEvent, on_delete=models.CASCADE, related_name="change_logs")
    action_type = models.CharField(max_length=20, choices=ACTION_CHOICES, db_index=True)
    old_start_datetime = models.DateTimeField(null=True, blank=True)
    old_end_datetime = models.DateTimeField(null=True, blank=True)
    new_start_datetime = models.DateTimeField(null=True, blank=True)
    new_end_datetime = models.DateTimeField(null=True, blank=True)
    old_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20, blank=True)
    reason = models.TextField(blank=True)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="schedule_change_logs")
    changed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-changed_at", "-id"]
        verbose_name = "Historique emploi du temps"
        verbose_name_plural = "Historiques emploi du temps"

    def __str__(self):
        return f"{self.event} - {self.action_type}"


class AcademicScheduleExecutionLog(models.Model):
    event = models.ForeignKey(AcademicScheduleEvent, on_delete=models.CASCADE, related_name="execution_logs")
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    actual_teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="executed_schedule_events")
    notes = models.TextField(blank=True)
    is_completed = models.BooleanField(default=False)
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="completed_schedule_execution_logs", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Execution emploi du temps"
        verbose_name_plural = "Executions emploi du temps"

    def __str__(self):
        return f"{self.event} - execution"

    def clean(self):
        errors = {}
        if self.started_at and self.ended_at and self.started_at > self.ended_at:
            errors["ended_at"] = "La fin d'execution doit etre posterieure au debut."
        if self.is_completed and not self.completed_by:
            errors["completed_by"] = "Un responsable de cloture est requis quand l'execution est terminee."
        if errors:
            raise ValidationError(errors)
