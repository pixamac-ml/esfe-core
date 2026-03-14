from django.db import models
from django.contrib.auth import get_user_model
from django.templatetags.static import static
from django.utils import timezone
from django.core.exceptions import ValidationError

from branches.models import Branch

User = get_user_model()


# ==========================================
# VALIDATION AVATAR
# ==========================================
def validate_avatar_extension(value):
    allowed = ["jpg", "jpeg", "png", "webp"]

    ext = value.name.split(".")[-1].lower()

    if ext not in allowed:
        raise ValidationError("Format avatar non autorisé")


# ==========================================
# CHEMIN UPLOAD AVATAR
# ==========================================
def profile_upload_path(instance, filename):
    return f"profiles/{instance.user.id}/avatar/{filename}"


# ==========================================
# PROFILE
# ==========================================
class Profile(models.Model):

    ROLE_CHOICES = [
        ("superadmin", "Super Administrateur"),
        ("executive", "Direction"),
        ("admissions", "Admissions"),
        ("finance", "Finance"),
        ("teacher", "Enseignant"),
        ("student", "Étudiant"),
    ]

    # ---------------------------------
    # RELATION UTILISATEUR
    # ---------------------------------
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
        db_index=True
    )

    # ---------------------------------
    # RÔLE STAFF / UTILISATEUR
    # ---------------------------------
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        blank=True,
        db_index=True
    )

    # ---------------------------------
    # ANNEXE
    # ---------------------------------
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="staff_profiles",
        db_index=True
    )

    # ---------------------------------
    # IDENTITÉ PUBLIQUE
    # ---------------------------------
    avatar = models.ImageField(
        upload_to=profile_upload_path,
        validators=[validate_avatar_extension],
        blank=True,
        null=True
    )

    bio = models.TextField(
        blank=True,
        help_text="Présentation publique de l'utilisateur"
    )

    location = models.CharField(
        max_length=120,
        blank=True,
        db_index=True
    )

    website = models.URLField(blank=True)

    main_domain = models.CharField(
        max_length=120,
        blank=True,
        help_text="Domaine principal d'activité",
        db_index=True
    )

    # ---------------------------------
    # RÉPUTATION
    # ---------------------------------
    reputation = models.IntegerField(
        default=0,
        db_index=True
    )

    # ---------------------------------
    # STATISTIQUES COMMUNAUTAIRES
    # ---------------------------------
    total_topics = models.PositiveIntegerField(
        default=0,
        db_index=True
    )

    total_answers = models.PositiveIntegerField(default=0)

    total_accepted_answers = models.PositiveIntegerField(default=0)

    total_upvotes_received = models.PositiveIntegerField(default=0)

    total_views_generated = models.PositiveIntegerField(default=0)

    # ---------------------------------
    # BADGES
    # ---------------------------------
    badge_gold = models.PositiveIntegerField(default=0)
    badge_silver = models.PositiveIntegerField(default=0)
    badge_bronze = models.PositiveIntegerField(default=0)

    # ---------------------------------
    # MÉTADONNÉES
    # ---------------------------------
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )

    updated_at = models.DateTimeField(auto_now=True)

    last_seen = models.DateTimeField(
        default=timezone.now,
        db_index=True
    )

    is_public = models.BooleanField(
        default=True,
        db_index=True
    )

    # ==========================================
    # META
    # ==========================================
    class Meta:
        ordering = ["-reputation"]
        verbose_name = "Profil"
        verbose_name_plural = "Profils"

        indexes = [
            models.Index(fields=["role"]),
            models.Index(fields=["branch"]),
            models.Index(fields=["reputation"]),
        ]

    # ==========================================
    # MÉTHODES
    # ==========================================
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