from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from news.models import Category, Program, News

User = get_user_model()


class Command(BaseCommand):
    help = "Seed initial des actualités institutionnelles"

    def handle(self, *args, **kwargs):

        self.stdout.write("🚀 Initialisation des actualités...")

        # ==================================================
        # AUTEUR
        # ==================================================
        admin_user = User.objects.first()

        # ==================================================
        # CATÉGORIES
        # ==================================================
        categories_data = [
            ("Vie académique", 1),
            ("Annonces officielles", 2),
            ("Événements", 3),
            ("Résultats", 4),
        ]

        categories = {}

        for name, order in categories_data:
            cat, _ = Category.objects.get_or_create(
                nom=name,
                defaults={
                    "slug": name.lower().replace(" ", "-"),
                    "ordre": order,
                    "is_active": True,
                }
            )
            categories[name] = cat

        # ==================================================
        # PROGRAMS (liaison facultative)
        # ==================================================
        programs_data = [
            "Licence Infirmier d’État",
            "Master en Santé Publique",
        ]

        programs = {}

        for name in programs_data:
            prog, _ = Program.objects.get_or_create(
                nom=name,
                defaults={
                    "slug": name.lower().replace(" ", "-"),
                    "description": f"Actualités liées au programme {name}.",
                    "is_active": True,
                }
            )
            programs[name] = prog

        # ==================================================
        # NEWS
        # ==================================================
        news_data = [

            {
                "titre": "Ouverture officielle des inscriptions 2025-2026",
                "resume": "Les inscriptions pour l’année académique 2025-2026 sont officiellement ouvertes.",
                "contenu": """
L’École de Santé Félix Houphouët-Boigny annonce l’ouverture officielle des inscriptions pour l’année académique 2025-2026.

Les candidats sont invités à déposer leurs dossiers conformément aux exigences académiques en vigueur.

Les programmes de Licence et Master sont accessibles sous conditions d’admission définies par la direction pédagogique.
""",
                "categorie": categories["Annonces officielles"],
                "program": None,
                "is_important": True,
                "is_urgent": False,
                "status": News.STATUS_PUBLISHED,
            },

            {
                "titre": "Cérémonie de rentrée académique",
                "resume": "La rentrée académique se tiendra dans l’amphithéâtre principal.",
                "contenu": """
La cérémonie officielle de rentrée académique réunira les étudiants, enseignants et partenaires institutionnels.

La direction présentera les orientations stratégiques et les nouvelles réformes pédagogiques.
""",
                "categorie": categories["Événements"],
                "program": None,
                "is_important": False,
                "is_urgent": False,
                "status": News.STATUS_PUBLISHED,
            },

            {
                "titre": "Résultats du semestre publiés",
                "resume": "Les résultats du semestre sont désormais disponibles.",
                "contenu": """
Les étudiants peuvent consulter leurs résultats via l’espace académique sécurisé.

Toute réclamation doit être déposée dans un délai de 72 heures.
""",
                "categorie": categories["Résultats"],
                "program": programs["Licence Infirmier d’État"],
                "is_important": False,
                "is_urgent": True,
                "status": News.STATUS_PUBLISHED,
            },

            {
                "titre": "Conférence sur la santé publique",
                "resume": "Conférence internationale sur les enjeux sanitaires en Afrique.",
                "contenu": """
Une conférence internationale réunira des experts en santé publique afin d’échanger sur les stratégies de prévention et de gestion des crises sanitaires.

Les étudiants du Master en Santé Publique sont invités à participer activement.
""",
                "categorie": categories["Vie académique"],
                "program": programs["Master en Santé Publique"],
                "is_important": True,
                "is_urgent": False,
                "status": News.STATUS_PUBLISHED,
            },

            {
                "titre": "Mise à jour du règlement intérieur",
                "resume": "Le règlement intérieur a été actualisé.",
                "contenu": """
La direction informe l’ensemble des étudiants que le règlement intérieur a été mis à jour.

Les nouvelles dispositions sont applicables immédiatement.
""",
                "categorie": categories["Annonces officielles"],
                "program": None,
                "is_important": False,
                "is_urgent": False,
                "status": News.STATUS_DRAFT,
            },

        ]

        for data in news_data:

            News.objects.update_or_create(
                titre=data["titre"],
                defaults={
                    "resume": data["resume"],
                    "contenu": data["contenu"],
                    "categorie": data["categorie"],
                    "program": data["program"],
                    "is_important": data["is_important"],
                    "is_urgent": data["is_urgent"],
                    "status": data["status"],
                    "auteur": admin_user,
                    "published_at": timezone.now() if data["status"] == News.STATUS_PUBLISHED else None,
                }
            )

        self.stdout.write(self.style.SUCCESS("✅ Seed News terminé proprement."))