from django.core.management.base import BaseCommand
from formations.models import (
    Cycle, Diploma, Filiere,
    Programme, ProgrammeYear, Fee
)


class Command(BaseCommand):
    help = "Seed complet Licence + Master ESFE"

    def handle(self, *args, **kwargs):

        # ==============================
        # RÉCUPÉRATION DES CYCLES
        # ==============================

        licence = Cycle.objects.get(slug="cycle-licence")
        master = Cycle.objects.get(slug="cycle-master")

        diploma_sup, _ = Diploma.objects.get_or_create(
            name="Diplôme Supérieur",
            defaults={"level": "superieur"}
        )

        filiere_sante, _ = Filiere.objects.get_or_create(
            name="Sciences de la santé"
        )

        # =====================================================
        # 🔵 BLOC LICENCE
        # =====================================================

        FORMATIONS_LICENCE = [
            {
                "title": "Infirmier d’État",
                "duration": 3,
                "description": "Formation professionnelle complète en soins infirmiers cliniques et communautaires.",
            },
            {
                "title": "Sage-Femme",
                "duration": 3,
                "description": "Formation spécialisée en santé maternelle, accouchement sécurisé et soins néonatals.",
            },
            {
                "title": "Biologie Médicale",
                "duration": 3,
                "description": "Formation en analyses biologiques, microbiologie et diagnostic médical.",
            },
            {
                "title": "Technicien Supérieur en Pharmacie",
                "duration": 3,
                "description": "Formation en gestion pharmaceutique et dispensation des produits de santé.",
            },
            {
                "title": "Santé Communautaire",
                "duration": 3,
                "description": "Formation orientée vers la prévention et la gestion des programmes sanitaires communautaires.",
            },
            {
                "title": "Nutritionniste",
                "duration": 3,
                "description": "Formation en nutrition humaine et sécurité alimentaire.",
            },
            {
                "title": "Santé Environnementale",
                "duration": 3,
                "description": "Formation en prévention des risques sanitaires liés à l’environnement.",
            },
            {
                "title": "Technicien Supérieur en Dialyse",
                "duration": 3,
                "description": "Formation spécialisée en techniques d’hémodialyse.",
            },
            {
                "title": "Optométrie",
                "duration": 3,
                "description": "Formation spécialisée en examen visuel et correction optique.",
            },
            {
                "title": "Aide-soignant",
                "duration": 1,
                "description": "Formation courte en assistance directe aux soins infirmiers.",
            },
            {
                "title": "Auxiliaire Infirmier",
                "duration": 2,
                "description": "Formation professionnalisante en appui aux soins cliniques.",
            },
            {
                "title": "Employé de Pharmacie",
                "duration": 2,
                "description": "Formation technique en assistance pharmaceutique.",
            },
            {
                "title": "Agent de Santé Communautaire",
                "duration": 2,
                "description": "Formation orientée vers la sensibilisation et la prévention en milieu communautaire.",
            },
        ]

        for data in FORMATIONS_LICENCE:

            programme, _ = Programme.objects.update_or_create(
                title=data["title"],
                defaults={
                    "cycle": licence,
                    "filiere": filiere_sante,
                    "diploma_awarded": diploma_sup,
                    "duration_years": data["duration"],
                    "short_description": data["description"],
                    "description": data["description"],
                    "learning_outcomes": "Compétences professionnelles adaptées au secteur sanitaire.",
                    "career_opportunities": "Structures publiques, privées et ONG.",
                    "is_active": True,
                }
            )

            programme.years.all().delete()

            for year in range(1, data["duration"] + 1):
                year_obj = ProgrammeYear.objects.create(
                    programme=programme,
                    year_number=year
                )

                Fee.objects.create(programme_year=year_obj, label="Inscription", amount=150000, due_month="Octobre")
                Fee.objects.create(programme_year=year_obj, label="Janvier", amount=150000, due_month="Janvier")
                Fee.objects.create(programme_year=year_obj, label="Mars", amount=150000, due_month="Mars")

        # =====================================================
        # 🔴 BLOC MASTER
        # =====================================================

        FORMATIONS_MASTER = [
            "Santé Communautaire",
            "Épidémiologie",
            "Manager en Santé",
            "Biochimie",
            "Nutrition",
            "Santé Environnementale",
            "Suivi et Évaluation",
            "Attaché de Recherche Clinique",
            "Data Manager",
        ]

        for title in FORMATIONS_MASTER:

            programme, _ = Programme.objects.update_or_create(
                title=f"Master en {title}",
                defaults={
                    "cycle": master,
                    "filiere": filiere_sante,
                    "diploma_awarded": diploma_sup,
                    "duration_years": 2,
                    "short_description": f"Formation avancée en {title.lower()}.",
                    "description": f"Le Master en {title} forme des experts capables d’intervenir au niveau stratégique et institutionnel.",
                    "learning_outcomes": "Expertise avancée, analyse stratégique, leadership.",
                    "career_opportunities": "Ministères, ONG internationales, instituts de recherche.",
                    "is_active": True,
                }
            )

            programme.years.all().delete()

            for year in range(1, 3):
                year_obj = ProgrammeYear.objects.create(
                    programme=programme,
                    year_number=year
                )

                Fee.objects.create(programme_year=year_obj, label="Inscription", amount=500000, due_month="Octobre")
                Fee.objects.create(programme_year=year_obj, label="Janvier", amount=250000, due_month="Janvier")
                Fee.objects.create(programme_year=year_obj, label="Mars", amount=250000, due_month="Mars")

        self.stdout.write(self.style.SUCCESS("🎓 Seed Licence + Master terminé proprement."))