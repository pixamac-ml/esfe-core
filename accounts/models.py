from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.templatetags.static import static
from django.utils import timezone

from branches.models import Branch

User = get_user_model()


def validate_avatar_extension(value):
    allowed = ["jpg", "jpeg", "png", "webp"]
    ext = value.name.split(".")[-1].lower()
    if ext not in allowed:
        raise ValidationError("Format avatar non autorise")


def profile_upload_path(instance, filename):
    return f"profiles/{instance.user.id}/avatar/{filename}"


class Profile(models.Model):
    ROLE_CHOICES = [
        ("superadmin", "Super Administrateur"),
        ("executive", "Direction"),
        ("admissions", "Admissions"),
        ("finance", "Finance"),
        ("teacher", "Enseignant"),
        ("student", "Etudiant"),
    ]

    POSITION_CHOICES = [
        ("student", "Etudiant"),
        ("teacher", "Enseignant"),
        ("finance_manager", "Responsable finance"),
        ("payment_agent", "Agent de paiement"),
        ("secretary", "Secretaire"),
        ("admissions", "Admissions"),
        ("director_of_studies", "Directeur des etudes"),
        ("executive_director", "Direction executive"),
        ("branch_manager", "Gestionnaire annexe"),
        ("academic_supervisor", "Surveillant academique"),
        ("super_admin", "Super administrateur"),
    ]

    USER_TYPE_CHOICES = [
        ("public", "Public"),
        ("staff", "Staff"),
    ]

    EMPLOYMENT_STATUS_CHOICES = [
        ("active", "Actif"),
        ("on_leave", "En conge"),
        ("suspended", "Suspendu"),
        ("inactive", "Inactif"),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
        db_index=True,
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        blank=True,
        db_index=True,
    )

    user_type = models.CharField(
        max_length=20,
        choices=USER_TYPE_CHOICES,
        blank=True,
        db_index=True,
        help_text="Type utilisateur normalise pour le portail",
    )

    position = models.CharField(
        max_length=40,
        choices=POSITION_CHOICES,
        blank=True,
        db_index=True,
        help_text="Fonction metier principale pour le routage dashboard.",
    )

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="staff_profiles",
        db_index=True,
    )

    employee_code = models.CharField(
        max_length=30,
        blank=True,
        db_index=True,
        help_text="Code employe interne pour la gestion de paie.",
    )

    salary_base = models.PositiveBigIntegerField(
        default=0,
        help_text="Salaire mensuel de base en FCFA.",
    )

    employment_status = models.CharField(
        max_length=20,
        choices=EMPLOYMENT_STATUS_CHOICES,
        default="active",
        db_index=True,
    )

    hire_date = models.DateField(
        null=True,
        blank=True,
    )

    avatar = models.ImageField(
        upload_to=profile_upload_path,
        validators=[validate_avatar_extension],
        blank=True,
        null=True,
    )

    bio = models.TextField(
        blank=True,
        help_text="Presentation publique de l'utilisateur",
    )

    location = models.CharField(
        max_length=120,
        blank=True,
        db_index=True,
    )

    website = models.URLField(blank=True)

    main_domain = models.CharField(
        max_length=120,
        blank=True,
        help_text="Domaine principal d'activite",
        db_index=True,
    )

    reputation = models.IntegerField(default=0, db_index=True)
    total_topics = models.PositiveIntegerField(default=0, db_index=True)
    total_answers = models.PositiveIntegerField(default=0)
    total_accepted_answers = models.PositiveIntegerField(default=0)
    total_upvotes_received = models.PositiveIntegerField(default=0)
    total_views_generated = models.PositiveIntegerField(default=0)

    badge_gold = models.PositiveIntegerField(default=0)
    badge_silver = models.PositiveIntegerField(default=0)
    badge_bronze = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_seen = models.DateTimeField(default=timezone.now, db_index=True)
    is_public = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["-reputation"]
        verbose_name = "Profil"
        verbose_name_plural = "Profils"
        indexes = [
            models.Index(fields=["role"]),
            models.Index(fields=["user_type"]),
            models.Index(fields=["position"]),
            models.Index(fields=["branch"]),
            models.Index(fields=["employment_status"]),
            models.Index(fields=["reputation"]),
        ]

    def __str__(self):
        return f"Profil de {self.user.username}"

    @property
    def avatar_url(self):
        if self.avatar and hasattr(self.avatar, "url"):
            return self.avatar.url
        return static("images/default-avatar.png")

    @property
    def score(self):
        return self.reputation

    @property
    def is_staff_member(self):
        return self.role in ["executive", "admissions", "finance"]

    @property
    def is_student(self):
        return self.role == "student"

    @property
    def is_teacher(self):
        return self.role == "teacher"


class PayrollEntry(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_READY = "ready"
    STATUS_PARTIAL = "partial"
    STATUS_PAID = "paid"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Brouillon"),
        (STATUS_READY, "Pret a payer"),
        (STATUS_PARTIAL, "Paiement partiel"),
        (STATUS_PAID, "Paye"),
    ]

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="payroll_entries",
        db_index=True,
    )

    employee = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="payroll_entries",
        db_index=True,
    )

    period_month = models.DateField(
        db_index=True,
        help_text="Premier jour du mois de paie.",
    )

    base_salary = models.PositiveBigIntegerField(default=0)
    allowances = models.PositiveBigIntegerField(default=0)
    deductions = models.PositiveBigIntegerField(default=0)
    advances = models.PositiveBigIntegerField(default=0)
    paid_amount = models.PositiveBigIntegerField(default=0)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True,
    )

    paid_at = models.DateTimeField(null=True, blank=True, db_index=True)
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_payroll_entries",
    )

    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_payroll_entries",
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-period_month", "employee__last_name", "employee__first_name"]
        verbose_name = "Fiche de paie"
        verbose_name_plural = "Fiches de paie"
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "employee", "period_month"],
                name="accounts_unique_branch_employee_payroll_period",
            )
        ]
        indexes = [
            models.Index(fields=["branch", "period_month"]),
            models.Index(fields=["employee", "period_month"]),
            models.Index(fields=["status", "period_month"]),
        ]

    def __str__(self):
        return f"Paie {self.employee} - {self.period_month:%Y-%m}"

    @property
    def net_salary(self):
        gross = self.base_salary + self.allowances
        charges = self.deductions + self.advances
        return max(gross - charges, 0)

    @property
    def remaining_salary(self):
        return max(self.net_salary - self.paid_amount, 0)

    def refresh_status(self):
        if self.paid_amount >= self.net_salary and self.net_salary > 0:
            self.status = self.STATUS_PAID
            if not self.paid_at:
                self.paid_at = timezone.now()
        elif self.paid_amount > 0:
            self.status = self.STATUS_PARTIAL
            self.paid_at = timezone.now()
        elif self.status == self.STATUS_PAID:
            self.status = self.STATUS_READY
            self.paid_at = None

    def save(self, *args, **kwargs):
        self.refresh_status()
        super().save(*args, **kwargs)
