from django.db import models
from django.contrib.auth import get_user_model
from django.templatetags.static import static
from django.utils import timezone

User = get_user_model()

# PROFILE
# ==========================================
from django.db import models
from django.contrib.auth import get_user_model
from django.templatetags.static import static
from django.utils import timezone


# ==========================================
# CHEMIN UPLOAD AVATAR
# ==========================================
def profile_upload_path(instance, filename):
    """
    Organisation propre des avatars
    profiles/<user_id>/avatar/<filename>
    """
    return f"profiles/{instance.user.id}/avatar/{filename}"


# ==========================================
# PROFILE
# ==========================================
class Profile(models.Model):

    # -----------------------------
    # RELATION UTILISATEUR
    # -----------------------------
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
        db_index=True
    )

    # -----------------------------
    # IDENTITÉ PUBLIQUE
    # -----------------------------
    avatar = models.ImageField(
        upload_to=profile_upload_path,
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

    website = models.URLField(
        blank=True
    )

    main_domain = models.CharField(
        max_length=120,
        blank=True,
        help_text="Domaine principal d'activité",
        db_index=True
    )

    # -----------------------------
    # RÉPUTATION
    # -----------------------------
    reputation = models.IntegerField(
        default=0,
        db_index=True
    )

    # -----------------------------
    # STATISTIQUES COMMUNAUTAIRES
    # -----------------------------
    total_topics = models.PositiveIntegerField(
        default=0,
        db_index=True
    )

    total_answers = models.PositiveIntegerField(
        default=0
    )

    total_accepted_answers = models.PositiveIntegerField(
        default=0
    )

    total_upvotes_received = models.PositiveIntegerField(
        default=0
    )

    total_views_generated = models.PositiveIntegerField(
        default=0
    )

    # -----------------------------
    # BADGES (compteurs rapides)
    # -----------------------------
    badge_gold = models.PositiveIntegerField(
        default=0
    )

    badge_silver = models.PositiveIntegerField(
        default=0
    )

    badge_bronze = models.PositiveIntegerField(
        default=0
    )

    # -----------------------------
    # MÉTADONNÉES
    # -----------------------------
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

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

    # ==========================================
    # MÉTHODES
    # ==========================================
    def __str__(self):
        return f"Profil de {self.user.username}"

    @property
    def avatar_url(self):
        """
        Retourne l'avatar utilisateur ou une image par défaut
        """
        if self.avatar and hasattr(self.avatar, "url"):
            return self.avatar.url

        return static("images/default-avatar.png")

    @property
    def score(self):
        """
        Score rapide utilisé dans l'UI
        """
        return self.reputation