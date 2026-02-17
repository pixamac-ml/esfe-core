from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model

from news.models import News, Category


class Command(BaseCommand):
    help = "Crée des actualités de démonstration"

    def handle(self, *args, **kwargs):

        User = get_user_model()
        user = User.objects.first()

        if not user:
            self.stdout.write(self.style.ERROR("Aucun utilisateur trouvé."))
            return

        # -------------------------
        # Catégories
        # -------------------------
        categories_data = [
            ("Événements", "evenements"),
            ("Académique", "academique"),
            ("Partenariats", "partenariats"),
        ]

        categories = {}
        for name, slug in categories_data:
            category, _ = Category.objects.get_or_create(
                slug=slug,
                defaults={"nom": name}
            )
            categories[slug] = category

        # -------------------------
        # Actualités
        # -------------------------
        news_data = [
            {
                "titre": "Lancement officiel de la rentrée académique 2026",
                "resume": "La rentrée académique 2026 a été officiellement lancée en présence de la direction et des étudiants.",
                "contenu": """
La rentrée académique 2026 a débuté dans une atmosphère dynamique et ambitieuse.

La direction a rappelé l'engagement de l'établissement envers l'excellence académique et l'innovation pédagogique.

Les étudiants ont découvert les laboratoires modernes et les nouvelles infrastructures.
                """,
                "categorie": categories["evenements"],
            },
            {
                "titre": "Séminaire sur l’innovation et la transformation digitale",
                "resume": "Un séminaire dédié à l’innovation et à l’intelligence artificielle a réuni étudiants et professionnels.",
                "contenu": """
Un séminaire exceptionnel a été organisé autour des enjeux de la transformation digitale.

Les thèmes abordés incluent l’automatisation, la cybersécurité et l’impact de l’IA dans l’éducation.
                """,
                "categorie": categories["academique"],
            },
            {
                "titre": "Journée portes ouvertes 2026 : forte mobilisation",
                "resume": "La journée portes ouvertes a permis aux visiteurs de découvrir les formations et infrastructures.",
                "contenu": """
Les visiteurs ont exploré les filières, les laboratoires et les opportunités offertes par l’établissement.

Une forte mobilisation a marqué cette édition 2026.
                """,
                "categorie": categories["evenements"],
            },
            {
                "titre": "Signature d’un partenariat académique international",
                "resume": "Un partenariat stratégique a été signé avec une institution étrangère.",
                "contenu": """
Cet accord permettra des échanges d’enseignants, des mobilités étudiantes et des projets de recherche communs.

Il renforce la dimension internationale de l’établissement.
                """,
                "categorie": categories["partenariats"],
            },
            {
                "titre": "Formation pratique en laboratoire : immersion totale",
                "resume": "Les étudiants ont participé à une session pratique intensive en laboratoire.",
                "contenu": """
Encadrés par leurs enseignants, les étudiants ont réalisé des simulations professionnelles et des études de cas.

Cette approche renforce les compétences pratiques.
                """,
                "categorie": categories["academique"],
            },
        ]

        created_count = 0

        for item in news_data:
            news, created = News.objects.get_or_create(
                titre=item["titre"],
                defaults={
                    "resume": item["resume"],
                    "contenu": item["contenu"],
                    "categorie": item["categorie"],
                    "status": News.STATUS_PUBLISHED,
                    "published_at": timezone.now(),
                    "auteur": user,
                },
            )

            if created:
                created_count += 1

        self.stdout.write(
            self.style.SUCCESS(f"{created_count} actualités créées avec succès.")
        )
