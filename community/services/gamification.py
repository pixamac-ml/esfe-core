"""
Service de gamification - Gère les XP, badges et niveaux
"""
from django.db.models import F

from community.models_gamification import (
    GamificationProfile,
    XPConfig,
    BadgeDefinition,
    UserBadge,
)


class GamificationService:
    """Service central de gamification"""

    # Cache des configs XP
    _xp_config_cache = None

    # Valeurs par défaut si pas de config en DB
    DEFAULT_XP = {
        "create_topic": 15,
        "create_answer": 10,
        "answer_accepted": 50,
        "receive_upvote": 5,
        "give_upvote": 1,
        "daily_login": 2,
        "streak_7days": 25,
        "streak_30days": 100,
        "complete_profile": 30,
        "first_topic_of_day": 20,
    }

    @classmethod
    def get_xp_config(cls):
        """Récupère la config XP avec cache"""
        if cls._xp_config_cache is None:
            try:
                cls._xp_config_cache = {
                    config.action: config.points
                    for config in XPConfig.objects.filter(is_active=True)
                }
            except Exception:
                cls._xp_config_cache = {}

        # Fusionner avec les valeurs par défaut
        return {**cls.DEFAULT_XP, **cls._xp_config_cache}

    @classmethod
    def get_or_create_profile(cls, user):
        """Récupère ou crée le profil gamification"""
        profile, created = GamificationProfile.objects.get_or_create(user=user)
        return profile

    @classmethod
    def award_xp(cls, user, action, **kwargs):
        """
        Attribue des XP pour une action

        Args:
            user: L'utilisateur
            action: Code de l'action (ex: "create_topic")

        Returns:
            tuple: (points_awarded, level_up)
        """
        config = cls.get_xp_config()
        points = config.get(action, 0)

        if points == 0:
            return 0, False

        profile = cls.get_or_create_profile(user)
        level_up = profile.add_xp(points, action)

        # Mettre à jour les stats selon l'action
        update_fields = []

        if action == "create_topic":
            profile.topics_created = F("topics_created") + 1
            update_fields.append("topics_created")
        elif action == "create_answer":
            profile.answers_given = F("answers_given") + 1
            update_fields.append("answers_given")
        elif action == "answer_accepted":
            profile.answers_accepted = F("answers_accepted") + 1
            update_fields.append("answers_accepted")
        elif action == "receive_upvote":
            profile.upvotes_received = F("upvotes_received") + 1
            update_fields.append("upvotes_received")
        elif action == "give_upvote":
            profile.upvotes_given = F("upvotes_given") + 1
            update_fields.append("upvotes_given")

        if update_fields:
            GamificationProfile.objects.filter(pk=profile.pk).update(
                **{field: F(field) + 1 for field in update_fields}
            )

        # Vérifier les badges
        cls.check_badges(user)

        return points, level_up

    @classmethod
    def check_badges(cls, user):
        """Vérifie et attribue les badges mérités"""
        profile = cls.get_or_create_profile(user)
        # Rafraîchir depuis la DB
        profile.refresh_from_db()

        new_badges = []

        # Badges déjà obtenus
        owned_codes = set(
            UserBadge.objects.filter(user=user).values_list("badge__code", flat=True)
        )

        # Vérifier chaque badge
        for badge in BadgeDefinition.objects.filter(is_active=True):
            if badge.code in owned_codes:
                continue

            if cls._check_badge_conditions(profile, badge):
                UserBadge.objects.create(user=user, badge=badge)

                # XP bonus
                if badge.xp_reward > 0:
                    profile.add_xp(badge.xp_reward, f"badge_{badge.code}")

                new_badges.append(badge)

        return new_badges

    @classmethod
    def _check_badge_conditions(cls, profile, badge):
        """Vérifie si les conditions du badge sont remplies"""
        cond = badge.conditions

        checks = [
            ("answers_count", profile.answers_given),
            ("accepted_answers", profile.answers_accepted),
            ("upvotes_received", profile.upvotes_received),
            ("topics_count", profile.topics_created),
            ("streak_days", profile.current_streak),
            ("level", profile.level),
        ]

        for key, value in checks:
            if key in cond and value < cond[key]:
                return False

        return True

    @classmethod
    def update_daily_streak(cls, user):
        """Met à jour la série quotidienne"""
        profile = cls.get_or_create_profile(user)
        updated = profile.update_streak()

        if updated:
            # Bonus XP pour les séries
            if profile.current_streak == 7:
                cls.award_xp(user, "streak_7days")
            elif profile.current_streak == 30:
                cls.award_xp(user, "streak_30days")

            cls.check_badges(user)

        return profile.current_streak

    @classmethod
    def get_leaderboard(cls, category="xp", limit=10):
        """Récupère le classement"""
        order_fields = {
            "xp": "-total_xp",
            "answers": "-answers_given",
            "accepted": "-answers_accepted",
        }

        order = order_fields.get(category, "-total_xp")

        return (
            GamificationProfile.objects
            .select_related("user", "user__profile")
            .order_by(order)[:limit]
        )