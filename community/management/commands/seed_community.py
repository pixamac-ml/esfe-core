from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Profile
from community.models import Answer, Category, Tag, Topic
from community.models_gamification import BadgeDefinition, GamificationProfile, UserBadge, XPConfig

User = get_user_model()


class Command(BaseCommand):
    help = "Seed demo data for the community area"

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="DemoCommunity123!",
            help="Password assigned to demo users.",
        )

    def handle(self, *args, **options):
        password = options["password"]

        with transaction.atomic():
            self.stdout.write(self.style.WARNING("Seeding community demo data..."))

            xps = self._seed_xp_config()
            badges = self._seed_badges()
            users = self._seed_users(password)
            categories = self._seed_categories()
            tags = self._seed_tags()
            topics = self._seed_topics(users, categories, tags)
            self._seed_badge_awards(users, badges)
            self._seed_gamification(users)
            self._seed_xp_transactions(users, xps)

        self.stdout.write(
            self.style.SUCCESS(
                "Community seeded successfully with realistic demo data."
            )
        )

    def _seed_xp_config(self):
        configs = [
            ("create_topic", 25, "Création d’un nouveau sujet"),
            ("create_answer", 15, "Réponse apportée à la communauté"),
            ("answer_accepted", 40, "Réponse acceptée par l’auteur"),
            ("receive_upvote", 3, "Vote positif reçu"),
            ("give_upvote", 1, "Vote positif donné"),
            ("daily_login", 5, "Connexion quotidienne"),
            ("complete_profile", 20, "Profil complété"),
        ]

        created = {}
        for action, points, description in configs:
            created[action], _ = XPConfig.objects.update_or_create(
                action=action,
                defaults={
                    "points": points,
                    "description": description,
                    "is_active": True,
                },
            )
        return created

    def _seed_badges(self):
        definitions = [
            {
                "code": "community_first_topic",
                "name": "Première prise de parole",
                "description": "A publié son premier sujet dans la communauté.",
                "icon": "🗣️",
                "color": "#2563EB",
                "category": "contribution",
                "rarity": "common",
                "conditions": {"topics_created": 1},
                "xp_reward": 25,
                "order": 1,
            },
            {
                "code": "community_helpful_voice",
                "name": "Voix utile",
                "description": "A apporté plusieurs réponses utiles à la communauté.",
                "icon": "💬",
                "color": "#0F766E",
                "category": "quality",
                "rarity": "uncommon",
                "conditions": {"answers_given": 3},
                "xp_reward": 50,
                "order": 2,
            },
            {
                "code": "community_guide",
                "name": "Guide",
                "description": "Réponses validées et présence régulière.",
                "icon": "🧭",
                "color": "#7C3AED",
                "category": "author",
                "rarity": "rare",
                "conditions": {"answers_accepted": 2},
                "xp_reward": 80,
                "order": 3,
            },
            {
                "code": "community_anchor",
                "name": "Point d’ancrage",
                "description": "Anime les discussions et garde les sujets en mouvement.",
                "icon": "⭐",
                "color": "#D97706",
                "category": "special",
                "rarity": "epic",
                "conditions": {"total_xp": 300},
                "xp_reward": 120,
                "order": 4,
            },
        ]

        created = {}
        for data in definitions:
            created[data["code"]], _ = BadgeDefinition.objects.update_or_create(
                code=data["code"],
                defaults=data,
            )
        return created

    def _seed_users(self, password):
        users = {}
        demo_users = [
            {
                "username": "amina.traore",
                "email": "amina.traore@example.com",
                "first_name": "Amina",
                "last_name": "Traoré",
                "profile": {
                    "role": "teacher",
                    "user_type": "staff",
                    "position": "teacher",
                    "bio": "Enseignante en sciences cliniques, active sur les sujets de pédagogie et de planning.",
                    "location": "Bamako",
                    "phone": "+223 70 11 22 33",
                    "main_domain": "Pédagogie clinique",
                    "reputation": 420,
                    "total_topics": 2,
                    "total_answers": 4,
                    "total_accepted_answers": 1,
                    "total_upvotes_received": 18,
                },
                "gamification": {
                    "total_xp": 540,
                    "level": 5,
                    "topics_created": 2,
                    "answers_given": 4,
                    "answers_accepted": 1,
                    "upvotes_received": 18,
                    "upvotes_given": 6,
                    "current_streak": 9,
                    "longest_streak": 14,
                },
            },
            {
                "username": "ibrahim.diallo",
                "email": "ibrahim.diallo@example.com",
                "first_name": "Ibrahim",
                "last_name": "Diallo",
                "profile": {
                    "role": "executive",
                    "user_type": "staff",
                    "position": "director_of_studies",
                    "bio": "Direction des études. Supervise le planning, les arbitrages pédagogiques et les annonces clés.",
                    "location": "Bamako",
                    "phone": "+223 70 44 55 66",
                    "main_domain": "Direction des études",
                    "reputation": 610,
                    "total_topics": 3,
                    "total_answers": 5,
                    "total_accepted_answers": 3,
                    "total_upvotes_received": 27,
                },
                "gamification": {
                    "total_xp": 820,
                    "level": 6,
                    "topics_created": 3,
                    "answers_given": 5,
                    "answers_accepted": 3,
                    "upvotes_received": 27,
                    "upvotes_given": 4,
                    "current_streak": 12,
                    "longest_streak": 19,
                },
            },
            {
                "username": "fatou.kone",
                "email": "fatou.kone@example.com",
                "first_name": "Fatou",
                "last_name": "Koné",
                "profile": {
                    "role": "student",
                    "user_type": "public",
                    "position": "student",
                    "bio": "Étudiante en deuxième année, très active sur les sujets de méthode et d’évaluation.",
                    "location": "Bamako",
                    "phone": "+223 70 77 88 99",
                    "main_domain": "Vie étudiante",
                    "reputation": 240,
                    "total_topics": 2,
                    "total_answers": 2,
                    "total_accepted_answers": 0,
                    "total_upvotes_received": 12,
                },
                "gamification": {
                    "total_xp": 310,
                    "level": 4,
                    "topics_created": 2,
                    "answers_given": 2,
                    "answers_accepted": 0,
                    "upvotes_received": 12,
                    "upvotes_given": 3,
                    "current_streak": 6,
                    "longest_streak": 11,
                },
            },
            {
                "username": "moussa.sissoko",
                "email": "moussa.sissoko@example.com",
                "first_name": "Moussa",
                "last_name": "Sissoko",
                "profile": {
                    "role": "student",
                    "user_type": "public",
                    "position": "student",
                    "bio": "Étudiant curieux, souvent présent sur les discussions de stage et de révision.",
                    "location": "Bamako",
                    "phone": "+223 70 22 33 44",
                    "main_domain": "Stages et évaluation",
                    "reputation": 185,
                    "total_topics": 1,
                    "total_answers": 3,
                    "total_accepted_answers": 0,
                    "total_upvotes_received": 7,
                },
                "gamification": {
                    "total_xp": 220,
                    "level": 3,
                    "topics_created": 1,
                    "answers_given": 3,
                    "answers_accepted": 0,
                    "upvotes_received": 7,
                    "upvotes_given": 5,
                    "current_streak": 4,
                    "longest_streak": 9,
                },
            },
            {
                "username": "souleymane.camara",
                "email": "souleymane.camara@example.com",
                "first_name": "Souleymane",
                "last_name": "Camara",
                "profile": {
                    "role": "teacher",
                    "user_type": "staff",
                    "position": "teacher",
                    "bio": "Enseignant de terrain, intervient souvent sur les consignes de stage et les retours pratiques.",
                    "location": "Bamako",
                    "phone": "+223 70 55 66 77",
                    "main_domain": "Stages cliniques",
                    "reputation": 300,
                    "total_topics": 1,
                    "total_answers": 3,
                    "total_accepted_answers": 1,
                    "total_upvotes_received": 14,
                },
                "gamification": {
                    "total_xp": 390,
                    "level": 4,
                    "topics_created": 1,
                    "answers_given": 3,
                    "answers_accepted": 1,
                    "upvotes_received": 14,
                    "upvotes_given": 2,
                    "current_streak": 7,
                    "longest_streak": 13,
                },
            },
        ]

        for item in demo_users:
            user, _ = User.objects.update_or_create(
                username=item["username"],
                defaults={
                    "email": item["email"],
                    "first_name": item["first_name"],
                    "last_name": item["last_name"],
                },
            )
            user.set_password(password)
            user.save(update_fields=["password"])

            profile_defaults = item["profile"]
            profile, _ = Profile.objects.update_or_create(
                user=user,
                defaults=profile_defaults,
            )
            users[item["username"]] = {
                "user": user,
                "profile": profile,
                "gamification": item["gamification"],
            }

        return users

    def _seed_categories(self):
        definitions = [
            {
                "name": "Pédagogie et cours",
                "description": "Méthodes, explications de cours et organisation pédagogique.",
                "order": 1,
                "icon": "book",
                "color": "#2563EB",
            },
            {
                "name": "Planning et emplois du temps",
                "description": "Programmation des séances, horaires et ajustements de semaine.",
                "order": 2,
                "icon": "calendar",
                "color": "#0F766E",
            },
            {
                "name": "Examens et évaluations",
                "description": "Barèmes, contrôles, notes et périodes d’évaluation.",
                "order": 3,
                "icon": "clipboard-check",
                "color": "#7C3AED",
            },
            {
                "name": "Stages et terrain clinique",
                "description": "Retours d’expérience, consignes et suivi de stage.",
                "order": 4,
                "icon": "briefcase-medical",
                "color": "#D97706",
            },
            {
                "name": "Vie étudiante",
                "description": "Organisation quotidienne, questions pratiques et entraide.",
                "order": 5,
                "icon": "users",
                "color": "#DC2626",
            },
            {
                "name": "Annonces académiques",
                "description": "Communications officielles, décisions et rappels importants.",
                "order": 6,
                "icon": "bullhorn",
                "color": "#475569",
            },
        ]

        categories = {}
        for item in definitions:
            categories[item["name"]], _ = Category.objects.update_or_create(
                name=item["name"],
                defaults=item,
            )
        return categories

    def _seed_tags(self):
        definitions = [
            ("planning", "Planning et horaires"),
            ("cours", "Cours et contenu pédagogique"),
            ("revision", "Révision et méthode"),
            ("examen", "Examens et barèmes"),
            ("stage", "Stage clinique"),
            ("annonce", "Annonce importante"),
            ("entraide", "Entraide entre membres"),
            ("retour", "Retour d’expérience"),
        ]

        tags = {}
        for name, description in definitions:
            tags[name], _ = Tag.objects.update_or_create(
                name=name,
                defaults={
                    "description": description,
                    "usage_count": 0,
                },
            )
        return tags

    def _seed_topics(self, users, categories, tags):
        now = timezone.now()

        topic_specs = [
            {
                "title": "Planning de la semaine: comment afficher clairement les cours du lundi au samedi ?",
                "author": users["ibrahim.diallo"]["user"],
                "category": categories["Planning et emplois du temps"],
                "content": (
                    "Nous avons plusieurs séquences à afficher sur la même semaine et il faut éviter les trous visuels. "
                    "L’idée est de garder la lecture simple, avec les créneaux vraiment programmés et les alertes visibles."
                ),
                "is_pinned": True,
                "view_count": 124,
                "days_ago": 8,
                "tags": ["planning", "cours", "annonce"],
                "answers": [
                    {
                        "author": users["amina.traore"]["user"],
                        "content": (
                            "Le plus clair est de séparer les créneaux fixes des créneaux exceptionnels. "
                            "Les blocs doivent rester lisibles avec une couleur courte, un intitulé court et une date visible."
                        ),
                        "upvotes": 8,
                    },
                    {
                        "author": users["fatou.kone"]["user"],
                        "content": (
                            "Oui, surtout si on garde la même logique sur toute la semaine: cela évite les pages qui donnent "
                            "l’impression d’être vides alors qu’il y a bien des cours programmés."
                        ),
                        "upvotes": 4,
                    },
                ],
                "accepted_index": 0,
                "last_activity_days": 1,
            },
            {
                "title": "Faut-il centraliser les demandes de reprogrammation de cours dans la communauté ?",
                "author": users["souleymane.camara"]["user"],
                "category": categories["Pédagogie et cours"],
                "content": (
                    "Quand un cours doit être déplacé, on perd du temps si la demande passe par plusieurs canaux. "
                    "Je propose un sujet unique pour regrouper les demandes, les décisions et les réponses de suivi."
                ),
                "is_pinned": False,
                "view_count": 76,
                "days_ago": 12,
                "tags": ["cours", "retour", "entraide"],
                "answers": [
                    {
                        "author": users["ibrahim.diallo"]["user"],
                        "content": (
                            "Oui, à condition de garder une règle simple: une demande = un titre clair + une date + un impact précis. "
                            "Le sujet devient alors exploitable par tout le monde."
                        ),
                        "upvotes": 11,
                    }
                ],
                "accepted_index": 0,
                "last_activity_days": 2,
            },
            {
                "title": "Stage clinique: quelles consignes avant l’accueil des étudiants en service ?",
                "author": users["souleymane.camara"]["user"],
                "category": categories["Stages et terrain clinique"],
                "content": (
                    "On a besoin d’une fiche courte: tenue, horaires, comportement, documents à apporter et interlocuteur référent. "
                    "Le but est d’éviter les répétitions à chaque rentrée de stage."
                ),
                "is_pinned": True,
                "view_count": 98,
                "days_ago": 15,
                "tags": ["stage", "annonce", "retour"],
                "answers": [
                    {
                        "author": users["amina.traore"]["user"],
                        "content": (
                            "Je recommande une note fixe en tête de sujet et une checklist en puces. "
                            "C’est le format le plus rapide à relire avant la descente en service."
                        ),
                        "upvotes": 9,
                    },
                    {
                        "author": users["moussa.sissoko"]["user"],
                        "content": (
                            "De notre côté, une version imprimable du rappel serait utile, surtout pour les étudiants qui consultent moins souvent le portail."
                        ),
                        "upvotes": 5,
                    },
                ],
                "accepted_index": 0,
                "last_activity_days": 3,
            },
            {
                "title": "Comment structurer une séance de révision avant l’examen de fin de module ?",
                "author": users["fatou.kone"]["user"],
                "category": categories["Examens et évaluations"],
                "content": (
                    "Je cherche une structure simple pour une séance de révision efficace: durée, priorités, exercice final "
                    "et façon de traiter les points de blocage les plus fréquents."
                ),
                "is_pinned": False,
                "view_count": 67,
                "days_ago": 10,
                "tags": ["revision", "examen", "cours"],
                "answers": [
                    {
                        "author": users["amina.traore"]["user"],
                        "content": (
                            "Un bon format: 15 minutes de rappel, 20 minutes de cas pratiques, 10 minutes de correction, "
                            "puis 10 minutes de questions ouvertes. On garde le rythme et on évite le surchargement."
                        ),
                        "upvotes": 10,
                    }
                ],
                "accepted_index": 0,
                "last_activity_days": 4,
            },
            {
                "title": "Retour sur les horaires de rattrapage du vendredi après-midi",
                "author": users["moussa.sissoko"]["user"],
                "category": categories["Vie étudiante"],
                "content": (
                    "Plusieurs étudiants demandent un créneau lisible pour les rattrapages du vendredi. "
                    "Il faut une annonce claire, un horaire fixe et une liste des salles ou espaces concernés."
                ),
                "is_pinned": False,
                "view_count": 53,
                "days_ago": 6,
                "tags": ["planning", "revision", "entraide"],
                "answers": [],
                "accepted_index": None,
                "last_activity_days": 6,
            },
            {
                "title": "Annonce officielle: la communauté reste un espace commun, sans séparation par annexe",
                "author": users["ibrahim.diallo"]["user"],
                "category": categories["Annonces académiques"],
                "content": (
                    "Ce sujet sert de référence: tout le monde voit les mêmes discussions, les mêmes annonces et les mêmes réponses. "
                    "On garde donc une logique commune, avec les bons filtres et une présentation propre."
                ),
                "is_pinned": True,
                "view_count": 141,
                "days_ago": 3,
                "tags": ["annonce", "cours", "entraide"],
                "answers": [
                    {
                        "author": users["fatou.kone"]["user"],
                        "content": (
                            "C’est plus simple à suivre comme ça. On retrouve tout au même endroit, sans devoir chercher dans plusieurs espaces."
                        ),
                        "upvotes": 7,
                    }
                ],
                "accepted_index": 0,
                "last_activity_days": 1,
            },
        ]

        created_topics = {}
        for spec in topic_specs:
            topic, _ = Topic.objects.update_or_create(
                title=spec["title"],
                defaults={
                    "author": spec["author"],
                    "category": spec["category"],
                    "content": spec["content"],
                    "is_pinned": spec["is_pinned"],
                    "view_count": spec["view_count"],
                    "is_published": True,
                    "is_locked": False,
                    "is_public": True,
                    "is_deleted": False,
                },
            )
            topic.tags.set([tags[tag_name] for tag_name in spec["tags"]])

            topic_answers = []
            for answer_spec in spec["answers"]:
                answer, _ = Answer.objects.update_or_create(
                    topic=topic,
                    author=answer_spec["author"],
                    content=answer_spec["content"],
                    defaults={
                        "upvotes": answer_spec["upvotes"],
                        "downvotes": 0,
                        "is_deleted": False,
                    },
                )
                topic_answers.append(answer)

            if spec["accepted_index"] is not None and topic_answers:
                accepted = topic_answers[spec["accepted_index"]]
                topic.accepted_answer = accepted
            elif spec["answers"]:
                topic.accepted_answer = topic_answers[0]
            else:
                topic.accepted_answer = None

            topic.save()

            topic_created_at = now - timedelta(days=spec["days_ago"])
            topic_last_activity_at = now - timedelta(days=spec["last_activity_days"])
            Topic.objects.filter(pk=topic.pk).update(
                created_at=topic_created_at,
                updated_at=topic_last_activity_at,
                last_activity_at=topic_last_activity_at,
            )

            for index, answer in enumerate(topic_answers, start=1):
                answer_created_at = topic_last_activity_at + timedelta(minutes=index * 7)
                Answer.objects.filter(pk=answer.pk).update(created_at=answer_created_at)

            created_topics[topic.title] = topic

        return created_topics

    def _seed_badge_awards(self, users, badges):
        awards = {
            "ibrahim.diallo": ["community_helpful_voice", "community_anchor"],
            "amina.traore": ["community_first_topic", "community_helpful_voice"],
            "fatou.kone": ["community_first_topic"],
            "moussa.sissoko": ["community_first_topic"],
            "souleymane.camara": ["community_helpful_voice", "community_guide"],
        }

        for username, badge_codes in awards.items():
            user = users[username]["user"]
            for badge_code in badge_codes:
                UserBadge.objects.get_or_create(
                    user=user,
                    badge=badges[badge_code],
                    defaults={"is_featured": True},
                )

    def _seed_gamification(self, users):
        for username, payload in users.items():
            data = payload["gamification"]
            GamificationProfile.objects.update_or_create(
                user=payload["user"],
                defaults={
                    "total_xp": data["total_xp"],
                    "level": data["level"],
                    "topics_created": data["topics_created"],
                    "answers_given": data["answers_given"],
                    "answers_accepted": data["answers_accepted"],
                    "upvotes_received": data["upvotes_received"],
                    "upvotes_given": data["upvotes_given"],
                    "current_streak": data["current_streak"],
                    "longest_streak": data["longest_streak"],
                    "custom_title": "Pilier communautaire" if username == "ibrahim.diallo" else "",
                },
            )

    def _seed_xp_transactions(self, users, xp_configs):
        transactions = [
            ("ibrahim.diallo", 40, "create_topic", "Annonce et cadrage de la communauté"),
            ("ibrahim.diallo", 15, "create_answer", "Réponse de validation sur le planning"),
            ("amina.traore", 25, "create_topic", "Publication d’un sujet pédagogique"),
            ("amina.traore", 15, "create_answer", "Réponse de méthode de révision"),
            ("fatou.kone", 25, "create_topic", "Question sur les révisions"),
            ("fatou.kone", 15, "create_answer", "Contribution sur la lisibilité du planning"),
            ("souleymane.camara", 25, "create_topic", "Sujet sur les consignes de stage"),
            ("souleymane.camara", 15, "create_answer", "Réponse d’encadrement"),
        ]

        for username, points, action, description in transactions:
            user = users[username]["user"]
            config = xp_configs.get(action)
            if config:
                points = config.points

            if not user.xp_transactions.filter(action=action, description=description).exists():
                user.xp_transactions.create(
                    points=points,
                    action=action,
                    description=description,
                    balance_after=user.gamification.total_xp,
                )
