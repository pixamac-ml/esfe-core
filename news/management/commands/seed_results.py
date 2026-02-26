from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.utils import timezone
from news.models import ResultSession


ACADEMIC_YEAR = "2025-2026"


class Command(BaseCommand):
    help = "Seed des résultats académiques 2025-2026"

    def handle(self, *args, **kwargs):

        self.stdout.write("📄 Initialisation des résultats académiques...")

        results_data = [

            {
                "type": "semestre",
                "titre": "Résultats Semestre 1",
                "annexe": "Moribabougou",
                "filiere": "Infirmier d’État",
                "classe": "Licence 1",
            },
            {
                "type": "semestre",
                "titre": "Résultats Semestre 2",
                "annexe": "Moribabougou",
                "filiere": "Biologie Médicale",
                "classe": "Licence 2",
            },
            {
                "type": "examen",
                "titre": "Résultats Examen National",
                "annexe": "Bamako Coura",
                "filiere": "Sage-Femme",
                "classe": "Licence 3",
            },
            {
                "type": "semestre",
                "titre": "Résultats Semestre 1",
                "annexe": "Sikasso",
                "filiere": "Master Santé Publique",
                "classe": "Master 1",
            },
        ]

        for data in results_data:

            result, created = ResultSession.objects.update_or_create(
                type=data["type"],
                titre=data["titre"],
                annee_academique=ACADEMIC_YEAR,
                annexe=data["annexe"],
                filiere=data["filiere"],
                classe=data["classe"],
                defaults={
                    "is_published": True,
                }
            )

            # Génération PDF minimal valide
            if created or not result.fichier_pdf:
                pdf_content = f"""
ESFE - RESULTATS OFFICIELS
Année académique : {ACADEMIC_YEAR}

Type : {result.get_type_display()}
Filière : {data['filiere']}
Classe : {data['classe']}
Annexe : {data['annexe']}

Ce document est généré automatiquement pour initialisation du système.
"""

                result.fichier_pdf.save(
                    f"resultats_{data['classe'].replace(' ', '_')}.pdf",
                    ContentFile(pdf_content.encode("utf-8")),
                    save=True
                )

        self.stdout.write(self.style.SUCCESS("✅ Seed résultats terminé proprement."))