from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from community.models import Category, Tag, Topic, Answer

User = get_user_model()


class Command(BaseCommand):
    help = "Seed Community test data"

    def handle(self, *args, **kwargs):

        self.stdout.write(self.style.WARNING("Seeding community data..."))

        # ======================
        # UTILISATEUR TEST
        # ======================
        user, _ = User.objects.get_or_create(
            username="admin_test",
            defaults={"email": "admin@test.com"}
        )
        user.set_password("password123")
        user.save()

        # ======================
        # CATÉGORIES (Domaines)
        # ======================
        bio, _ = Category.objects.get_or_create(name="Biologie médicale")
        obs, _ = Category.objects.get_or_create(name="Obstétrique")
        sp, _ = Category.objects.get_or_create(name="Santé publique")

        # ======================
        # TAGS
        # ======================
        tag_asepsie, _ = Tag.objects.get_or_create(name="Asepsie")
        tag_biochimie, _ = Tag.objects.get_or_create(name="Biochimie")
        tag_cas, _ = Tag.objects.get_or_create(name="Cas clinique")
        tag_pansement, _ = Tag.objects.get_or_create(name="Pansement")

        # ======================
        # TOPIC 1 (résolu)
        # ======================
        topic1 = Topic.objects.create(
            title="Comment réaliser un pansement stérile correctement ?",
            author=user,
            category=bio,
            content="Quelles sont les étapes précises pour réaliser un pansement stérile en milieu hospitalier ?",
            last_activity_at=timezone.now(),
        )

        topic1.tags.add(tag_asepsie, tag_pansement)

        answer1 = Answer.objects.create(
            topic=topic1,
            author=user,
            content="1. Lavage des mains\n2. Préparation du matériel stérile\n3. Désinfection\n4. Pose du pansement",
            upvotes=5
        )

        topic1.accepted_answer = answer1
        topic1.save()

        # ======================
        # TOPIC 2
        # ======================
        topic2 = Topic.objects.create(
            title="Interprétation d’un bilan biochimique",
            author=user,
            category=bio,
            content="Comment interpréter une élévation des transaminases ?",
        )

        topic2.tags.add(tag_biochimie, tag_cas)

        Answer.objects.create(
            topic=topic2,
            author=user,
            content="Une élévation des transaminases peut indiquer une atteinte hépatique.",
            upvotes=3
        )

        # ======================
        # TOPIC 3
        # ======================
        topic3 = Topic.objects.create(
            title="Gestion d’un accouchement compliqué",
            author=user,
            category=obs,
            content="Quelles sont les étapes à suivre en cas de complication lors d’un accouchement ?",
        )

        topic3.tags.add(tag_cas)

        Answer.objects.create(
            topic=topic3,
            author=user,
            content="Il faut évaluer rapidement la situation et alerter l’équipe médicale.",
            upvotes=2
        )

        self.stdout.write(self.style.SUCCESS("Community seeded successfully."))