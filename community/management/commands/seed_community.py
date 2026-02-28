import random
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from community.models import Category, Topic, Answer, Vote

User = get_user_model()


class Command(BaseCommand):
    help = "Génère des données fictives pour la communauté"

    def handle(self, *args, **kwargs):

        self.stdout.write("Création des données communauté...")

        # Créer utilisateur test si aucun
        if not User.objects.exists():
            user = User.objects.create_user(
                username="etudiant_test",
                password="12345678"
            )
        else:
            user = User.objects.first()

        categories_names = [
            "Biologie médicale",
            "Soins infirmiers",
            "Obstétrique",
            "Santé publique",
            "Pharmacologie"
        ]

        categories = []

        for name in categories_names:
            category, _ = Category.objects.get_or_create(name=name)
            categories.append(category)

        topics = []

        for i in range(20):
            topic = Topic.objects.create(
                title=f"Question pratique {i+1}",
                author=user,
                category=random.choice(categories),
                content="Contenu détaillé de la question académique."
            )
            topics.append(topic)

        for topic in topics:
            answers = []

            for i in range(random.randint(2, 5)):
                answer = Answer.objects.create(
                    topic=topic,
                    author=user,
                    content="Réponse structurée à la question."
                )
                answers.append(answer)

                # Réponse imbriquée
                if random.choice([True, False]):
                    Answer.objects.create(
                        topic=topic,
                        author=user,
                        content="Réponse à cette réponse.",
                        parent=answer
                    )

            # Votes
            for answer in answers:
                Vote.objects.create(
                    user=user,
                    answer=answer,
                    value=random.choice([1, -1])
                )

                answer.upvotes = answer.votes.filter(value=1).count()
                answer.downvotes = answer.votes.filter(value=-1).count()
                answer.save()

        self.stdout.write(self.style.SUCCESS("Données générées avec succès."))