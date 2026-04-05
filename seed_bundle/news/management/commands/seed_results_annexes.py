from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from news.models import ResultSession

ACADEMIC_YEAR = "2025-2026"


class Command(BaseCommand):
    help = "Seed résultats par annexe (Moribabougou & Djélibougou)"

    def handle(self, *args, **kwargs):

        self.stdout.write("📄 Seed résultats par annexe...")

        ANNEXES = {

            "Moribabougou": [
                ("Infirmier d’État", "Licence 1"),
                ("Infirmier d’État", "Licence 2"),
                ("Infirmier d’État", "Licence 3"),
                ("Biologie Médicale", "Licence 1"),
                ("Sage-Femme", "Licence 3"),
            ],

            "Djélibougou": [
                ("Infirmier d’État", "Licence 1"),
                ("Santé Communautaire", "Licence 2"),
                ("Biologie Médicale", "Licence 3"),
                ("Master Santé Publique", "Master 1"),
                ("Master Santé Publique", "Master 2"),
            ],
        }

        TYPES = [
            ("semestre", "Résultats Semestre 1"),
            ("semestre", "Résultats Semestre 2"),
            ("examen", "Résultats Examen National"),
        ]

        for annexe, formations in ANNEXES.items():

            self.stdout.write(f"➡️  Traitement annexe : {annexe}")

            for filiere, classe in formations:

                for type_code, titre in TYPES:

                    result, created = ResultSession.objects.update_or_create(
                        type=type_code,
                        titre=titre,
                        annee_academique=ACADEMIC_YEAR,
                        annexe=annexe,
                        filiere=filiere,
                        classe=classe,
                        defaults={
                            "is_published": True
                        }
                    )

                    if created or not result.fichier_pdf:

                        pdf_content = f"""
ESFE - RESULTATS OFFICIELS
Année académique : {ACADEMIC_YEAR}

Annexe : {annexe}
Filière : {filiere}
Classe : {classe}
Type : {result.get_type_display()}

Document officiel généré pour initialisation du système.
"""

                        filename = f"{annexe}_{classe}_{type_code}.pdf"
                        filename = filename.replace(" ", "_")

                        result.fichier_pdf.save(
                            filename,
                            ContentFile(pdf_content.encode("utf-8")),
                            save=True
                        )

        self.stdout.write(self.style.SUCCESS("✅ Seed résultats Moribabougou & Djélibougou terminé."))