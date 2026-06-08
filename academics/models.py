from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from branches.models import Branch
from formations.models import Programme
from inscriptions.models import Inscription

from academics.services.grading import apply_ec_grade
from academics.services.semester import compute_semester_result
from academics.services.ue import compute_ue_result


class Language(models.Model):
    name = models.CharField(max_length=120, unique=True)
    code = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Langue"
        verbose_name_plural = "Langues"

    def __str__(self):
        return self.name


class Profession(models.Model):
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Metier"
        verbose_name_plural = "Metiers"

    def __str__(self):
        return self.name


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

    admissibility_gap = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("2.00"),
        help_text="Marge d'admissibilité en points sous le seuil. Ex: 2 = admissible si moyenne ≥ seuil - 2.",
    )

    is_active = models.BooleanField(default=True, db_index=True)
    is_archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)

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
    STATUS_ACTIVE = "ACTIVE"
    STATUS_ARCHIVED = "ARCHIVED"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_SUSPENDED = "SUSPENDED"
    STATUS_TRANSFERRED = "TRANSFERRED"
    STATUS_ABANDONED = "ABANDONED"

    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_ARCHIVED, "Archivee"),
        (STATUS_COMPLETED, "Terminee"),
        (STATUS_SUSPENDED, "Suspendue"),
        (STATUS_TRANSFERRED, "Transferee"),
        (STATUS_ABANDONED, "Abandonnee"),
    ]

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

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
    )
    is_active = models.BooleanField(default=True, db_index=True)
    is_archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)
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
            if not self.academic_class.is_active or self.academic_class.is_archived:
                errors["academic_class"] = "La classe academique cible doit etre active et non archivee."

            if self.academic_class.programme != self.programme:
                errors["academic_class"] = "La classe ne correspond pas au programme."

            if self.academic_class.branch != self.branch:
                errors["academic_class"] = "La classe ne correspond pas à l'annexe."

            if self.academic_class.academic_year != self.academic_year:
                errors["academic_class"] = "La classe ne correspond pas à l'année académique."

        if self.status == self.STATUS_ACTIVE and self.student_id and self.programme_id and self.academic_year_id:
            duplicate_active = AcademicEnrollment.objects.filter(
                student=self.student,
                programme=self.programme,
                academic_year=self.academic_year,
                status=self.STATUS_ACTIVE,
            ).exclude(pk=self.pk)
            if duplicate_active.exists():
                errors["status"] = (
                    "Un etudiant ne peut pas avoir deux inscriptions academiques actives "
                    "pour la meme annee et le meme programme."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        sync_fields = {"is_active", "is_archived", "archived_at"}
        if self.status == self.STATUS_ACTIVE:
            self.is_active = True
            self.is_archived = False
            self.archived_at = None
        elif self.status == self.STATUS_ARCHIVED:
            self.is_active = False
            self.is_archived = True
            if not self.archived_at:
                self.archived_at = timezone.now()
        else:
            self.is_active = False
            sync_fields = {"is_active"}
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | sync_fields
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


class LessonLog(models.Model):
    STATUS_PLANNED = "planned"
    STATUS_DONE = "done"
    STATUS_CANCELLED = "cancelled"
    STATUS_ABSENT_TEACHER = "absent_teacher"

    STATUS_CHOICES = [
        (STATUS_PLANNED, "Planifie"),
        (STATUS_DONE, "Fait"),
        (STATUS_CANCELLED, "Annule"),
        (STATUS_ABSENT_TEACHER, "Enseignant absent"),
    ]

    academic_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.PROTECT,
        related_name="lesson_logs",
    )
    ec = models.ForeignKey(
        EC,
        on_delete=models.PROTECT,
        related_name="lesson_logs",
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="lesson_logs",
    )
    schedule_event = models.ForeignKey(
        AcademicScheduleEvent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lesson_logs",
    )
    date = models.DateField(db_index=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PLANNED,
        db_index=True,
    )
    content = models.TextField(blank=True)
    homework = models.TextField(blank=True)
    observations = models.TextField(blank=True)
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="lesson_logs",
        db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_lesson_logs",
    )
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="validated_lesson_logs",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-start_time", "-id"]
        verbose_name = "Cahier de texte"
        verbose_name_plural = "Cahiers de texte"
        indexes = [
            models.Index(fields=["academic_class", "date"]),
            models.Index(fields=["teacher", "date"]),
            models.Index(fields=["branch", "date"]),
            models.Index(fields=["status", "date"]),
        ]

    def __str__(self):
        return f"{self.academic_class} - {self.ec} - {self.date}"

    def clean(self):
        errors = {}

        if self.start_time and self.end_time and self.start_time >= self.end_time:
            errors["end_time"] = "L'heure de fin doit etre posterieure a l'heure de debut."

        if self.academic_class_id and self.branch_id and self.academic_class.branch_id != self.branch_id:
            errors["branch"] = "L'annexe ne correspond pas a la classe academique."

        if self.ec_id and self.academic_class_id and self.ec.ue.semester.academic_class_id != self.academic_class_id:
            errors["ec"] = "La matiere ne correspond pas a la classe academique."

        if self.schedule_event_id:
            event = self.schedule_event
            if self.academic_class_id and event.academic_class_id != self.academic_class_id:
                errors["schedule_event"] = "L'evenement planifie ne correspond pas a la classe."
            elif self.ec_id and event.ec_id != self.ec_id:
                errors["schedule_event"] = "L'evenement planifie ne correspond pas a la matiere."
            elif self.teacher_id and event.teacher_id != self.teacher_id:
                errors["schedule_event"] = "L'evenement planifie ne correspond pas a l'enseignant."
            elif self.branch_id and event.branch_id != self.branch_id:
                errors["schedule_event"] = "L'evenement planifie ne correspond pas a l'annexe."

        if self.status == self.STATUS_DONE and not (self.content or "").strip():
            errors["content"] = "Le contenu du cours est obligatoire quand le cours est marque comme fait."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class WeeklyScheduleSlot(models.Model):
    """
    Grille hebdomadaire recurrente (jour + creneau horaire) pour une classe.
    Les seances reelles datees restent materialisees via AcademicScheduleEvent.
    """

    WEEKDAY_CHOICES = [
        (0, "Lundi"),
        (1, "Mardi"),
        (2, "Mercredi"),
        (3, "Jeudi"),
        (4, "Vendredi"),
        (5, "Samedi"),
        (6, "Dimanche"),
    ]

    academic_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.CASCADE,
        related_name="weekly_schedule_slots",
    )
    ec = models.ForeignKey(
        EC,
        on_delete=models.PROTECT,
        related_name="weekly_schedule_slots",
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="weekly_teaching_slots",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="weekly_schedule_slots",
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="weekly_schedule_slots",
    )
    weekday = models.IntegerField(choices=WEEKDAY_CHOICES, db_index=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_weekly_schedule_slots",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["weekday", "start_time", "id"]
        verbose_name = "Creneau hebdomadaire"
        verbose_name_plural = "Creneaux hebdomadaires"
        constraints = [
            models.UniqueConstraint(
                fields=["academic_class", "weekday", "start_time"],
                name="unique_weekly_slot_start_per_class_day",
            )
        ]
        indexes = [
            models.Index(fields=["branch", "academic_year", "weekday"]),
            models.Index(fields=["academic_class", "is_active"]),
        ]

    def __str__(self):
        return f"{self.academic_class} — {self.get_weekday_display()} {self.start_time}-{self.end_time}"

    def clean(self):
        errors = {}
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            errors["end_time"] = "L'heure de fin doit etre posterieure au debut."
        if self.academic_class_id and self.branch_id and self.academic_class.branch_id != self.branch_id:
            errors["branch"] = "L'annexe ne correspond pas a la classe."
        if self.academic_class_id and self.academic_year_id and self.academic_class.academic_year_id != self.academic_year_id:
            errors["academic_year"] = "L'annee academique ne correspond pas a la classe."
        if self.ec_id and self.academic_class_id and self.ec.ue.semester.academic_class_id != self.academic_class_id:
            errors["ec"] = "L'EC ne correspond pas a la classe."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class AcademicBulletin(models.Model):
    TYPE_SEMESTER = "semester"
    TYPE_ANNUAL = "annual"
    TYPE_CHOICES = [
        (TYPE_SEMESTER, "Bulletin semestriel"),
        (TYPE_ANNUAL, "Bulletin annuel"),
    ]

    STATUS_DRAFT = "draft"
    STATUS_GENERATED = "generated"
    STATUS_PUBLISHED = "published"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Brouillon"),
        (STATUS_GENERATED, "Genere"),
        (STATUS_PUBLISHED, "Publie"),
        (STATUS_CANCELLED, "Annule"),
    ]

    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="academic_bulletins",
    )
    enrollment = models.ForeignKey(
        AcademicEnrollment,
        on_delete=models.PROTECT,
        related_name="bulletins",
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="bulletins",
    )
    academic_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.PROTECT,
        related_name="bulletins",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="academic_bulletins",
    )
    semester = models.ForeignKey(
        Semester,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="bulletins",
    )
    bulletin_type = models.CharField(max_length=20, choices=TYPE_CHOICES, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    reference = models.CharField(max_length=60, unique=True, blank=True, db_index=True)
    average = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    total_credits = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    credits_obtained = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    decision = models.CharField(max_length=80, blank=True, db_index=True)
    mention = models.CharField(max_length=80, blank=True)
    snapshot = models.JSONField(default=dict, blank=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_academic_bulletins",
    )
    generated_at = models.DateTimeField(null=True, blank=True, db_index=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_academic_bulletins",
    )
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    pdf_file = models.FileField(upload_to="academics/bulletins/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "enrollment", "bulletin_type", "semester"],
                condition=models.Q(bulletin_type="semester"),
                name="academics_unique_semester_bulletin",
            ),
            models.UniqueConstraint(
                fields=["student", "enrollment", "bulletin_type"],
                condition=models.Q(bulletin_type="annual"),
                name="academics_unique_annual_bulletin",
            ),
        ]
        indexes = [
            models.Index(fields=["branch", "academic_year", "status"]),
            models.Index(fields=["academic_class", "bulletin_type", "status"]),
            models.Index(fields=["student", "academic_year"]),
        ]

    def __str__(self):
        return f"{self.reference} - {self.student}"

    def save(self, *args, **kwargs):
        if not self.reference and self.enrollment_id:
            prefix = "BUL-S" if self.bulletin_type == self.TYPE_SEMESTER else "BUL-A"
            suffix = f"-S{self.semester.number}" if self.semester_id else ""
            self.reference = (
                f"{prefix}-{self.enrollment.academic_year.name.replace('-', '')}-"
                f"{self.enrollment.branch.code.upper()}-{str(self.enrollment_id).zfill(5)}{suffix}"
            )
        super().save(*args, **kwargs)

    def clean(self):
        errors = {}
        if self.bulletin_type == self.TYPE_SEMESTER and not self.semester_id:
            errors["semester"] = "Un bulletin semestriel doit etre lie a un semestre."
        if self.bulletin_type == self.TYPE_ANNUAL and self.semester_id:
            errors["semester"] = "Un bulletin annuel ne doit pas etre lie a un semestre."
        if self.enrollment_id:
            if self.academic_year_id and self.enrollment.academic_year_id != self.academic_year_id:
                errors["academic_year"] = "L'annee ne correspond pas a l'inscription academique."
            if self.academic_class_id and self.enrollment.academic_class_id != self.academic_class_id:
                errors["academic_class"] = "La classe ne correspond pas a l'inscription academique."
            if self.branch_id and self.enrollment.branch_id != self.branch_id:
                errors["branch"] = "L'annexe ne correspond pas a l'inscription academique."
            if self.student_id and self.enrollment.student_id != self.student.user_id:
                errors["student"] = "L'etudiant ne correspond pas a l'inscription academique."
        if self.semester_id and self.academic_class_id and self.semester.academic_class_id != self.academic_class_id:
            errors["semester"] = "Le semestre ne correspond pas a la classe."
        if errors:
            raise ValidationError(errors)


class AcademicDiplomaAward(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_READY = "ready"
    STATUS_DELIVERED = "delivered"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Brouillon"),
        (STATUS_READY, "Pret"),
        (STATUS_DELIVERED, "Delivre"),
        (STATUS_CANCELLED, "Annule"),
    ]

    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="academic_diploma_awards",
    )
    enrollment = models.ForeignKey(
        AcademicEnrollment,
        on_delete=models.PROTECT,
        related_name="diploma_awards",
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="diploma_awards",
    )
    academic_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.PROTECT,
        related_name="diploma_awards",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="academic_diploma_awards",
    )
    programme = models.ForeignKey(
        Programme,
        on_delete=models.PROTECT,
        related_name="academic_diploma_awards",
    )
    diploma = models.ForeignKey(
        "formations.Diploma",
        on_delete=models.PROTECT,
        related_name="academic_awards",
    )
    reference = models.CharField(max_length=60, unique=True, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    final_average = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    mention = models.CharField(max_length=80, blank=True)
    decision = models.CharField(max_length=80, blank=True, db_index=True)
    awarded_at = models.DateField(null=True, blank=True)
    prepared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prepared_academic_diplomas",
    )
    delivered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="delivered_academic_diplomas",
    )
    delivered_at = models.DateTimeField(null=True, blank=True, db_index=True)
    snapshot = models.JSONField(default=dict, blank=True)
    pdf_file = models.FileField(upload_to="academics/diplomas/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "programme", "academic_year"],
                name="academics_unique_diploma_award_student_programme_year",
            )
        ]
        indexes = [
            models.Index(fields=["branch", "academic_year", "status"]),
            models.Index(fields=["student", "status"]),
            models.Index(fields=["programme", "status"]),
        ]

    def __str__(self):
        return f"{self.reference} - {self.student}"

    def save(self, *args, **kwargs):
        if not self.reference and self.enrollment_id:
            self.reference = (
                f"DIP-{self.enrollment.academic_year.name.replace('-', '')}-"
                f"{self.enrollment.branch.code.upper()}-{str(self.enrollment_id).zfill(5)}"
            )
        super().save(*args, **kwargs)

    def clean(self):
        errors = {}
        if self.enrollment_id:
            if self.student_id and self.enrollment.student_id != self.student.user_id:
                errors["student"] = "L'etudiant ne correspond pas a l'inscription academique."
            if self.academic_year_id and self.enrollment.academic_year_id != self.academic_year_id:
                errors["academic_year"] = "L'annee ne correspond pas a l'inscription academique."
            if self.academic_class_id and self.enrollment.academic_class_id != self.academic_class_id:
                errors["academic_class"] = "La classe ne correspond pas a l'inscription academique."
            if self.branch_id and self.enrollment.branch_id != self.branch_id:
                errors["branch"] = "L'annexe ne correspond pas a l'inscription academique."
            if self.programme_id and self.enrollment.programme_id != self.programme_id:
                errors["programme"] = "Le programme ne correspond pas a l'inscription academique."
        if self.programme_id and self.diploma_id and self.programme.diploma_awarded_id != self.diploma_id:
            errors["diploma"] = "Le diplome ne correspond pas au programme."
        if errors:
            raise ValidationError(errors)


class AcademicDebt(models.Model):
    """
    Dette academique : EC non valide qu'un etudiant doit repasser.
    Creee automatiquement quand un etudiant est declare ADMISSIBLE.
    """

    STATUS_PENDING = "pending"
    STATUS_CLEARED = "cleared"
    STATUS_CHOICES = [
        (STATUS_PENDING, "En attente"),
        (STATUS_CLEARED, "Soldee"),
    ]

    enrollment = models.ForeignKey(
        AcademicEnrollment,
        on_delete=models.PROTECT,
        related_name="academic_debts",
    )
    ec = models.ForeignKey(
        EC,
        on_delete=models.PROTECT,
        related_name="academic_debts",
    )
    semester = models.ForeignKey(
        Semester,
        on_delete=models.PROTECT,
        related_name="academic_debts",
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="academic_debts",
    )
    academic_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.PROTECT,
        related_name="academic_debts",
    )

    score_original = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="Note originale ayant cause la dette.",
    )
    score_retake = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        help_text="Note de repêchage (mise a jour quand l'EC est repasse).",
    )

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES,
        default=STATUS_PENDING, db_index=True,
    )
    carry_forward_to = models.ForeignKey(
        AcademicYear,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="carried_debts",
        help_text="Annee academique vers laquelle la dette est reportee.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    cleared_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Dette academique"
        verbose_name_plural = "Dettes academiques"
        constraints = [
            models.UniqueConstraint(
                fields=["enrollment", "ec", "semester", "academic_year"],
                name="academics_unique_debt_per_enrollment_ec_semester_year",
            )
        ]
        indexes = [
            models.Index(fields=["enrollment", "status"]),
            models.Index(fields=["ec", "status"]),
            models.Index(fields=["academic_year", "status"]),
            models.Index(fields=["academic_class", "status"]),
        ]

    def __str__(self):
        return f"Dette {self.enrollment} - {self.ec} (S{self.semester.number})"

    def clean(self):
        errors = {}
        if self.enrollment_id and self.ec_id:
            ec_semester = self.ec.ue.semester
            if ec_semester.id != self.semester_id:
                errors["ec"] = "L'EC n'appartient pas au semestre indique."
            if ec_semester.academic_class_id != self.enrollment.academic_class_id:
                errors["ec"] = "L'EC n'appartient pas a la classe de l'inscription."
        if self.enrollment_id:
            if self.academic_year_id and self.enrollment.academic_year_id != self.academic_year_id:
                errors["academic_year"] = "L'annee ne correspond pas a l'inscription."
            if self.academic_class_id and self.enrollment.academic_class_id != self.academic_class_id:
                errors["academic_class"] = "La classe ne correspond pas a l'inscription."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def mark_cleared(self, score_retake=None):
        self.status = self.STATUS_CLEARED
        if score_retake is not None:
            self.score_retake = Decimal(str(score_retake))
        self.cleared_at = timezone.now()
        self.save(update_fields=["status", "score_retake", "cleared_at", "updated_at"])


class AcademicDecisionLog(models.Model):
    """
    Journal d'audit des decisions annuelles (VALIDE / ADMISSIBLE / NON ADMIS).

    Enregistre a chaque generation de bulletins annuels pour une classe :
    - qui a lance le calcul
    - quels parametres ont ete utilises (seuil, marge)
    - combien d'etudiants dans chaque statut
    - quelles regles ont ete declenchees
    """

    academic_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.PROTECT,
        related_name="decision_logs",
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="decision_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="academic_decision_logs",
    )
    threshold = models.DecimalField(
        max_digits=4, decimal_places=2,
        help_text="Seuil de validation utilise.",
    )
    admissibility_gap = models.DecimalField(
        max_digits=4, decimal_places=2,
        help_text="Marge d'admissibilite utilisee.",
    )
    total_students = models.PositiveIntegerField(default=0)
    validated_count = models.PositiveIntegerField(default=0)
    admissible_count = models.PositiveIntegerField(default=0)
    non_admis_count = models.PositiveIntegerField(default=0)
    rule_codes_used = models.JSONField(default=list, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Journal de decision annuelle"
        verbose_name_plural = "Journaux de decisions annuelles"

    def __str__(self):
        return f"Decision {self.academic_class} - {self.academic_year} ({self.created_at.date()})"
