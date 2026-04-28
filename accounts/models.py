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


def branch_expense_upload_path(instance, filename):
    return f"branches/{instance.branch_id}/expenses/{filename}"


class BranchExpense(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_SUBMITTED = "submitted"
    STATUS_APPROVED = "approved"
    STATUS_PAID = "paid"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Brouillon"),
        (STATUS_SUBMITTED, "A valider"),
        (STATUS_APPROVED, "Approuvee"),
        (STATUS_PAID, "Payee"),
        (STATUS_REJECTED, "Rejetee"),
    ]

    CATEGORY_RENT = "rent"
    CATEGORY_UTILITIES = "utilities"
    CATEGORY_SUPPLIES = "supplies"
    CATEGORY_MAINTENANCE = "maintenance"
    CATEGORY_TRANSPORT = "transport"
    CATEGORY_COMMUNICATION = "communication"
    CATEGORY_OTHER = "other"

    CATEGORY_CHOICES = [
        (CATEGORY_RENT, "Loyer"),
        (CATEGORY_UTILITIES, "Eau / electricite"),
        (CATEGORY_SUPPLIES, "Fournitures"),
        (CATEGORY_MAINTENANCE, "Maintenance"),
        (CATEGORY_TRANSPORT, "Transport"),
        (CATEGORY_COMMUNICATION, "Communication"),
        (CATEGORY_OTHER, "Autre"),
    ]

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="expenses",
        db_index=True,
    )
    title = models.CharField(max_length=180)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default=CATEGORY_OTHER, db_index=True)
    amount = models.PositiveBigIntegerField()
    expense_date = models.DateField(default=timezone.localdate, db_index=True)
    supplier = models.CharField(max_length=150, blank=True)
    reference = models.CharField(max_length=80, blank=True, db_index=True)
    receipt = models.FileField(upload_to=branch_expense_upload_path, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SUBMITTED, db_index=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_branch_expenses")
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_branch_expenses")
    paid_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="paid_branch_expenses")
    approved_at = models.DateTimeField(null=True, blank=True, db_index=True)
    paid_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-expense_date", "-created_at"]
        verbose_name = "Depense annexe"
        verbose_name_plural = "Depenses annexes"
        indexes = [
            models.Index(fields=["branch", "expense_date"]),
            models.Index(fields=["branch", "status"]),
            models.Index(fields=["category", "expense_date"]),
        ]

    def __str__(self):
        return f"{self.title} - {self.amount} FCFA"

    @property
    def can_be_approved(self):
        return self.status in {self.STATUS_DRAFT, self.STATUS_SUBMITTED}

    @property
    def can_be_paid(self):
        return self.status == self.STATUS_APPROVED


class BranchCashMovement(models.Model):
    TYPE_IN = "in"
    TYPE_OUT = "out"

    TYPE_CHOICES = [
        (TYPE_IN, "Entree"),
        (TYPE_OUT, "Sortie"),
    ]

    SOURCE_MANUAL = "manual"
    SOURCE_EXPENSE = "expense"
    SOURCE_PAYROLL = "payroll"
    SOURCE_STUDENT_PAYMENT = "student_payment"
    SOURCE_ADJUSTMENT = "adjustment"

    SOURCE_CHOICES = [
        (SOURCE_MANUAL, "Saisie manuelle"),
        (SOURCE_EXPENSE, "Depense"),
        (SOURCE_PAYROLL, "Salaire"),
        (SOURCE_STUDENT_PAYMENT, "Paiement etudiant"),
        (SOURCE_ADJUSTMENT, "Ajustement caisse"),
    ]

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="cash_movements",
        db_index=True,
    )
    movement_type = models.CharField(max_length=10, choices=TYPE_CHOICES, db_index=True)
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES, default=SOURCE_MANUAL, db_index=True)
    amount = models.PositiveBigIntegerField()
    label = models.CharField(max_length=180)
    movement_date = models.DateField(default=timezone.localdate, db_index=True)
    expense = models.ForeignKey(
        BranchExpense,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cash_movements",
    )
    reference = models.CharField(max_length=80, blank=True, db_index=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_cash_movements")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-movement_date", "-created_at"]
        verbose_name = "Mouvement de caisse"
        verbose_name_plural = "Mouvements de caisse"
        indexes = [
            models.Index(fields=["branch", "movement_date"]),
            models.Index(fields=["branch", "movement_type"]),
            models.Index(fields=["source", "movement_date"]),
        ]

    def __str__(self):
        return f"{self.get_movement_type_display()} {self.amount} FCFA - {self.label}"
