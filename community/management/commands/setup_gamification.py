"""
Commande pour initialiser le système de gamification
"""
from django.core.management.base import BaseCommand
from community.models_gamification import BadgeDefinition, XPConfig


class Command(BaseCommand):
    help = "Initialise le système de gamification avec les badges et configs XP par défaut"

    def handle(self, *args, **options):
        self.stdout.write("🎮 Initialisation du système de gamification...")

        # ================================
        # CONFIGURATIONS XP
        # ================================
        xp_configs = [
            ("create_topic", 15, "Créer un nouveau sujet"),
            ("create_answer", 10, "Répondre à un sujet"),
            ("answer_accepted", 50, "Réponse acceptée comme solution"),
            ("receive_upvote", 5, "Recevoir un vote positif"),
            ("give_upvote", 1, "Donner un vote positif"),
            ("daily_login", 2, "Connexion quotidienne"),
            ("streak_7days", 25, "Série de 7 jours"),
            ("streak_30days", 100, "Série de 30 jours"),
            ("complete_profile", 30, "Profil complété"),
            ("first_topic_of_day", 20, "Premier sujet du jour"),
        ]

        for action, points, desc in xp_configs:
            obj, created = XPConfig.objects.get_or_create(
                action=action,
                defaults={"points": points, "description": desc}
            )
            if created:
                self.stdout.write(f"  ✓ XP Config: {action} = {points} XP")

        # ================================
        # BADGES
        # ================================
        badges = [
            # Contribution
            {
                "code": "first_answer",
                "name": "Premier Pas",
                "description": "Publiez votre première réponse",
                "icon": "💬",
                "category": "contribution",
                "rarity": "common",
                "conditions": {"answers_count": 1},
                "xp_reward": 10,
            },
            {
                "code": "talkative",
                "name": "Bavard",
                "description": "Publiez 10 réponses",
                "icon": "🗣️",
                "category": "contribution",
                "rarity": "common",
                "conditions": {"answers_count": 10},
                "xp_reward": 25,
            },
            {
                "code": "orator",
                "name": "Orateur",
                "description": "Publiez 50 réponses",
                "icon": "🎤",
                "category": "contribution",
                "rarity": "uncommon",
                "conditions": {"answers_count": 50},
                "xp_reward": 50,
            },
            {
                "code": "speaker",
                "name": "Conférencier",
                "description": "Publiez 100 réponses",
                "icon": "📢",
                "category": "contribution",
                "rarity": "rare",
                "conditions": {"answers_count": 100},
                "xp_reward": 100,
            },

            # Qualité
            {
                "code": "solver",
                "name": "Solutionneur",
                "description": "Votre première réponse acceptée",
                "icon": "✅",
                "category": "quality",
                "rarity": "common",
                "conditions": {"accepted_answers": 1},
                "xp_reward": 15,
            },
            {
                "code": "precise",
                "name": "Précis",
                "description": "5 réponses acceptées",
                "icon": "🎯",
                "category": "quality",
                "rarity": "uncommon",
                "conditions": {"accepted_answers": 5},
                "xp_reward": 50,
            },
            {
                "code": "sniper",
                "name": "Tireur d'élite",
                "description": "25 réponses acceptées",
                "icon": "🏹",
                "category": "quality",
                "rarity": "rare",
                "conditions": {"accepted_answers": 25},
                "xp_reward": 100,
            },
            {
                "code": "genius",
                "name": "Génie",
                "description": "100 réponses acceptées",
                "icon": "🧠",
                "category": "quality",
                "rarity": "epic",
                "conditions": {"accepted_answers": 100},
                "xp_reward": 250,
            },

            # Votes
            {
                "code": "appreciated",
                "name": "Apprécié",
                "description": "Recevez 10 votes positifs",
                "icon": "👍",
                "category": "votes",
                "rarity": "common",
                "conditions": {"upvotes_received": 10},
                "xp_reward": 15,
            },
            {
                "code": "popular",
                "name": "Populaire",
                "description": "Recevez 100 votes positifs",
                "icon": "🔥",
                "category": "votes",
                "rarity": "uncommon",
                "conditions": {"upvotes_received": 100},
                "xp_reward": 50,
            },
            {
                "code": "star",
                "name": "Star",
                "description": "Recevez 500 votes positifs",
                "icon": "⭐",
                "category": "votes",
                "rarity": "rare",
                "conditions": {"upvotes_received": 500},
                "xp_reward": 150,
            },

            # Auteur
            {
                "code": "curious",
                "name": "Curieux",
                "description": "Créez votre premier sujet",
                "icon": "✏️",
                "category": "author",
                "rarity": "common",
                "conditions": {"topics_count": 1},
                "xp_reward": 10,
            },
            {
                "code": "author",
                "name": "Auteur",
                "description": "Créez 10 sujets",
                "icon": "📝",
                "category": "author",
                "rarity": "uncommon",
                "conditions": {"topics_count": 10},
                "xp_reward": 30,
            },
            {
                "code": "writer",
                "name": "Écrivain",
                "description": "Créez 50 sujets",
                "icon": "📖",
                "category": "author",
                "rarity": "rare",
                "conditions": {"topics_count": 50},
                "xp_reward": 75,
            },

            # Streak
            {
                "code": "regular",
                "name": "Habitué",
                "description": "7 jours consécutifs actif",
                "icon": "📅",
                "category": "streak",
                "rarity": "common",
                "conditions": {"streak_days": 7},
                "xp_reward": 25,
            },
            {
                "code": "devoted",
                "name": "Dévoué",
                "description": "30 jours consécutifs actif",
                "icon": "🗓️",
                "category": "streak",
                "rarity": "rare",
                "conditions": {"streak_days": 30},
                "xp_reward": 100,
            },
            {
                "code": "pillar",
                "name": "Pilier",
                "description": "100 jours consécutifs actif",
                "icon": "🏛️",
                "category": "streak",
                "rarity": "epic",
                "conditions": {"streak_days": 100},
                "xp_reward": 300,
            },

            # Niveaux
            {
                "code": "level_5",
                "name": "Contributeur",
                "description": "Atteignez le niveau 5",
                "icon": "🌟",
                "category": "special",
                "rarity": "uncommon",
                "conditions": {"level": 5},
                "xp_reward": 50,
            },
            {
                "code": "level_10",
                "name": "Légende",
                "description": "Atteignez le niveau 10",
                "icon": "🔥",
                "category": "special",
                "rarity": "legendary",
                "conditions": {"level": 10},
                "xp_reward": 500,
            },
        ]

        for i, badge_data in enumerate(badges):
            badge_data["order"] = i
            code = badge_data.pop("code")

            obj, created = BadgeDefinition.objects.get_or_create(
                code=code,
                defaults=badge_data
            )
            if created:
                self.stdout.write(f"  ✓ Badge: {obj.icon} {obj.name}")

        self.stdout.write(self.style.SUCCESS("\n✅ Gamification initialisée avec succès!"))
        self.stdout.write(f"   - {XPConfig.objects.count()} configurations XP")
        self.stdout.write(f"   - {BadgeDefinition.objects.count()} badges")