"""
Système de Gamification - Modèles
XP, Niveaux, Badges, Classements, Récompenses
"""
from django.conf import settings
from django.db import models
from django.db.models import Index
from django.utils import timezone
import datetime


# ==========================
# CONFIGURATION XP
# ==========================
class XPConfig(models.Model):
    """Configuration des points XP par action"""

    ACTION_CHOICES = [
        ("create_topic", "Créer un sujet"),
        ("create_answer", "Répondre"),
        ("answer_accepted", "Réponse acceptée"),
        ("receive_upvote", "Recevoir un upvote"),
        ("give_upvote", "Donner un upvote"),
        ("daily_login", "Connexion quotidienne"),
        ("streak_7days", "Série 7 jours"),
        ("streak_30days", "Série 30 jours"),
        ("complete_profile", "Profil complété"),
        ("first_topic_of_day", "1er sujet du jour"),
    ]

    action = models.CharField(max_length=50, choices=ACTION_CHOICES, unique=True)
    points = models.IntegerField(default=0)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Configuration XP"
        verbose_name_plural = "Configurations XP"

    def __str__(self):
        return f"{self.get_action_display()} = {self.points} XP"


# ==========================
# PROFIL GAMIFICATION
# ==========================
class GamificationProfile(models.Model):
    """Extension du profil pour la gamification"""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="gamification"
    )

    # Points et niveau
    total_xp = models.PositiveIntegerField(default=0)
    level = models.PositiveIntegerField(default=1)

    # Statistiques
    topics_created = models.PositiveIntegerField(default=0)
    answers_given = models.PositiveIntegerField(default=0)
    answers_accepted = models.PositiveIntegerField(default=0)
    upvotes_received = models.PositiveIntegerField(default=0)
    upvotes_given = models.PositiveIntegerField(default=0)

    # Séries (streaks)
    current_streak = models.PositiveIntegerField(default=0)
    longest_streak = models.PositiveIntegerField(default=0)
    last_activity_date = models.DateField(null=True, blank=True)

    # Récompenses débloquées
    has_custom_flair = models.BooleanField(default=False)
    has_signature = models.BooleanField(default=False)
    has_gold_frame = models.BooleanField(default=False)
    custom_title = models.CharField(max_length=50, blank=True)

    # Dates
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Profil Gamification"
        verbose_name_plural = "Profils Gamification"
        indexes = [
            Index(fields=["total_xp"]),
            Index(fields=["level"]),
            Index(fields=["-total_xp"]),
        ]

    def __str__(self):
        return f"{self.user.username} - Niveau {self.level} ({self.total_xp} XP)"

    def add_xp(self, points, action=None):
        """Ajoute des XP et vérifie le passage de niveau"""
        self.total_xp += points
        new_level = self.calculate_level()
        level_up = new_level > self.level

        if level_up:
            self.level = new_level

        self.save(update_fields=["total_xp", "level", "updated_at"])

        # Logger l'XP
        XPTransaction.objects.create(
            user=self.user,
            points=points,
            action=action or "unknown",
            balance_after=self.total_xp
        )

        return level_up

    def calculate_level(self):
        """Calcule le niveau basé sur l'XP total"""
        xp = self.total_xp
        level = 1

        while self._xp_for_level(level + 1) <= xp:
            level += 1
            if level >= 10:
                break

        return level

    @staticmethod
    def _xp_for_level(level):
        """XP requis pour atteindre un niveau"""
        if level <= 1:
            return 0
        return level * (level - 1) * 50 + 100

    def xp_progress(self):
        """Pourcentage de progression vers le prochain niveau"""
        current_level_xp = self._xp_for_level(self.level)
        next_level_xp = self._xp_for_level(self.level + 1)

        if self.level >= 10:
            return 100

        progress = (self.total_xp - current_level_xp) / (next_level_xp - current_level_xp) * 100
        return min(100, max(0, progress))

    def xp_to_next_level(self):
        """XP restant pour le prochain niveau"""
        if self.level >= 10:
            return 0
        return self._xp_for_level(self.level + 1) - self.total_xp

    def update_streak(self):
        """Met à jour la série de connexions"""
        today = timezone.now().date()

        if self.last_activity_date is None:
            self.current_streak = 1
        elif self.last_activity_date == today:
            return False  # Déjà compté aujourd'hui
        elif self.last_activity_date == today - datetime.timedelta(days=1):
            self.current_streak += 1
        else:
            self.current_streak = 1

        self.longest_streak = max(self.longest_streak, self.current_streak)
        self.last_activity_date = today
        self.save(update_fields=["current_streak", "longest_streak", "last_activity_date"])
        return True

    def get_level_title(self):
        """Retourne le titre du niveau"""
        titles = {
            1: "Novice",
            2: "Apprenti",
            3: "Étudiant",
            4: "Initié",
            5: "Contributeur",
            6: "Mentor",
            7: "Expert",
            8: "Sage",
            9: "Maître",
            10: "Légende",
        }
        return titles.get(self.level, "Novice")

    def get_level_icon(self):
        """Retourne l'icône du niveau"""
        icons = {
            1: "🌱", 2: "🌿", 3: "📚", 4: "🎓", 5: "⭐",
            6: "🌟", 7: "💎", 8: "👑", 9: "🏆", 10: "🔥",
        }
        return icons.get(self.level, "🌱")


# ==========================
# TRANSACTIONS XP
# ==========================
class XPTransaction(models.Model):
    """Historique des transactions XP"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="xp_transactions"
    )

    points = models.IntegerField()
    action = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    balance_after = models.PositiveIntegerField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            Index(fields=["user", "-created_at"]),
        ]

    def __str__(self):
        sign = "+" if self.points > 0 else ""
        return f"{self.user.username}: {sign}{self.points} XP ({self.action})"


# ==========================
# DÉFINITION DES BADGES
# ==========================
class BadgeDefinition(models.Model):
    """Définition des badges disponibles"""

    RARITY_CHOICES = [
        ("common", "Commun"),
        ("uncommon", "Peu commun"),
        ("rare", "Rare"),
        ("epic", "Épique"),
        ("legendary", "Légendaire"),
    ]

    CATEGORY_CHOICES = [
        ("contribution", "Contribution"),
        ("quality", "Qualité"),
        ("votes", "Votes"),
        ("author", "Auteur"),
        ("streak", "Séries"),
        ("special", "Spécial"),
    ]

    # Identité
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField()

    # Visuel
    icon = models.CharField(max_length=10)
    icon_image = models.ImageField(upload_to="badges/", null=True, blank=True)
    color = models.CharField(max_length=20, default="#6B7280")

    # Classification
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    rarity = models.CharField(max_length=20, choices=RARITY_CHOICES, default="common")

    # Conditions (JSON)
    conditions = models.JSONField(
        default=dict,
        help_text="Ex: {'answers_count': 10}"
    )

    # Bonus
    xp_reward = models.PositiveIntegerField(default=0)

    # Ordre
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_secret = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category", "order"]
        verbose_name = "Définition de badge"
        verbose_name_plural = "Définitions de badges"

    def __str__(self):
        return f"{self.icon} {self.name} ({self.get_rarity_display()})"

    def get_rarity_color(self):
        """Couleur selon la rareté"""
        colors = {
            "common": "#9CA3AF",
            "uncommon": "#10B981",
            "rare": "#3B82F6",
            "epic": "#8B5CF6",
            "legendary": "#F59E0B",
        }
        return colors.get(self.rarity, "#9CA3AF")


# ==========================
# BADGES OBTENUS
# ==========================
class UserBadge(models.Model):
    """Badges obtenus par les utilisateurs"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_badges"
    )

    badge = models.ForeignKey(
        BadgeDefinition,
        on_delete=models.CASCADE,
        related_name="holders"
    )

    earned_at = models.DateTimeField(auto_now_add=True)
    is_featured = models.BooleanField(default=False)

    class Meta:
        unique_together = ["user", "badge"]
        ordering = ["-earned_at"]

    def __str__(self):
        return f"{self.user.username} - {self.badge.name}"


# ==========================
# CLASSEMENT
# ==========================
class LeaderboardEntry(models.Model):
    """Entrées du classement"""

    PERIOD_CHOICES = [
        ("weekly", "Hebdomadaire"),
        ("monthly", "Mensuel"),
        ("alltime", "Tout temps"),
    ]

    CATEGORY_CHOICES = [
        ("xp", "Points XP"),
        ("answers", "Réponses"),
        ("accepted", "Solutions"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="leaderboard_entries"
    )

    period = models.CharField(max_length=20, choices=PERIOD_CHOICES)
    period_start = models.DateField()
    period_end = models.DateField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    rank = models.PositiveIntegerField()
    score = models.PositiveIntegerField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["rank"]

    def __str__(self):
        return f"#{self.rank} {self.user.username} ({self.period})"