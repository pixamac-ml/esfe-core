import random
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from community.models import Category, Topic, Answer, Vote

User = get_user_model()


class Command(BaseCommand):
    help = "Seed communauté propre et relançable"

    @transaction.atomic
    def handle(self, *args, **kwargs):
        self.stdout.write("Seeding communauté...")

        user, _ = User.objects.get_or_create(
            username="etudiant_test",
            defaults={"password": "12345678"}
        )

        category_names = [
            "Biologie médicale",
            "Soins infirmiers",
            "Obstétrique",
            "Santé publique",
            "Pharmacologie"
        ]

        categories = []
        for index, name in enumerate(category_names):
            category, _ = Category.objects.get_or_create(
                name=name,
                defaults={"order": index}
            )
            categories.append(category)

        topics = []

        for i in range(15):
            topic, _ = Topic.objects.get_or_create(
                title=f"Question pratique {i+1}",
                defaults={
                    "author": user,
                    "category": random.choice(categories),
                    "content": "Contenu académique structuré pour test.",
                }
            )
            topics.append(topic)

        for topic in topics:
            for i in range(random.randint(2, 4)):
                answer = Answer.objects.create(
                    topic=topic,
                    author=user,
                    content="Réponse académique structurée."
                )

                if random.choice([True, False]):
                    Answer.objects.create(
                        topic=topic,
                        author=user,
                        content="Réponse imbriquée.",
                        parent=answer
                    )

                # Vote sécurisé (respecte UniqueConstraint)
                value = random.choice([Vote.UPVOTE, Vote.DOWNVOTE])

                Vote.objects.update_or_create(
                    user=user,
                    answer=answer,
                    defaults={"value": value}
                )

                # Mise à jour des compteurs propre
                answer.upvotes = answer.votes.filter(value=Vote.UPVOTE).count()
                answer.downvotes = answer.votes.filter(value=Vote.DOWNVOTE).count()
                answer.save(update_fields=["upvotes", "downvotes"])

        self.stdout.write(self.style.SUCCESS("Seed communauté terminé."))