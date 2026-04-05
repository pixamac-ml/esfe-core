from django.core.management.base import BaseCommand
from formations.models import (
    Cycle,
    Diploma,
    Filiere,
    Programme,
    ProgrammeYear,
    Fee,
)


ACADEMIC_YEAR = "2025-2026"


class Command(BaseCommand):
    help = "Seed académique ESFE 2025-2026 (Licence + Master officiel)"

    def handle(self, *args, **kwargs):

        self.stdout.write("🚀 Initialisation du seed ESFE 2025-2026...")

        # =====================================================
        # 🎓 CYCLES
        # =====================================================

        licence, _ = Cycle.objects.get_or_create(
            name="Licence",
            defaults={
                "min_duration_years": 1,
                "max_duration_years": 3,
                "theme": "accent",
                "description": "Cycle Licence ESFE",
                "is_active": True,
            }
        )

        master, _ = Cycle.objects.get_or_create(
            name="Master",
            defaults={
                "min_duration_years": 2,
                "max_duration_years": 2,
                "theme": "secondary",
                "description": "Cycle Master ESFE",
                "is_active": True,
            }
        )

        # =====================================================
        # 🎓 DIPLÔME
        # =====================================================

        diploma_sup, _ = Diploma.objects.get_or_create(
            name="Diplôme Supérieur en Sciences de la Santé",
            defaults={"level": "superieur"}
        )

        # =====================================================
        # 🏥 FILIÈRE
        # =====================================================

        filiere_sante, _ = Filiere.objects.get_or_create(
            name="Sciences de la Santé",
            defaults={"is_active": True}
        )

        # =====================================================
        # 🔵 LICENCE – 410 000 / AN
        # =====================================================

        LICENCE_PROGRAMMES = [
            "Infirmier d’État",
            "Sage-Femme",
            "Biologie Médicale",
        ]

        for title in LICENCE_PROGRAMMES:

            programme, _ = Programme.objects.update_or_create(
                title=title,
                defaults={
                    "cycle": licence,
                    "filiere": filiere_sante,
                    "diploma_awarded": diploma_sup,
                    "duration_years": 3,
                    "short_description": f"{title} – Année académique {ACADEMIC_YEAR}",
                    "description": f"Programme officiel {title} conforme à la fiche ESFE {ACADEMIC_YEAR}.",
                    "learning_outcomes": "Compétences cliniques, techniques et professionnelles.",
                    "career_opportunities": "Hôpitaux, cliniques, centres de santé, ONG.",
                    "is_active": True,
                }
            )

            # Nettoyage années si existantes
            programme.years.all().delete()

            for year_number in range(1, 4):

                year_obj = ProgrammeYear.objects.create(
                    programme=programme,
                    year_number=year_number
                )

                # TOTAL ANNUEL = 410 000
                Fee.objects.create(
                    programme_year=year_obj,
                    label="Inscription",
                    amount=130000,
                    due_month="Octobre"
                )

                Fee.objects.create(
                    programme_year=year_obj,
                    label="Janvier",
                    amount=140000,
                    due_month="Janvier"
                )

                Fee.objects.create(
                    programme_year=year_obj,
                    label="Mars",
                    amount=140000,
                    due_month="Mars"
                )

        # =====================================================
        # 🔴 MASTER
        # =====================================================

        MASTER_PROGRAMMES = [
            "Master en Santé Publique",
            "Master en Épidémiologie",
        ]

        for title in MASTER_PROGRAMMES:

            programme, _ = Programme.objects.update_or_create(
                title=title,
                defaults={
                    "cycle": master,
                    "filiere": filiere_sante,
                    "diploma_awarded": diploma_sup,
                    "duration_years": 2,
                    "short_description": f"{title} – Année académique {ACADEMIC_YEAR}",
                    "description": f"{title} structuré selon la grille officielle ESFE {ACADEMIC_YEAR}.",
                    "learning_outcomes": "Leadership, expertise stratégique et gestion des systèmes de santé.",
                    "career_opportunities": "Ministère de la Santé, ONG internationales, instituts de recherche.",
                    "is_active": True,
                }
            )

            programme.years.all().delete()

            # ===== Année 1 : 810 000 =====
            year1 = ProgrammeYear.objects.create(
                programme=programme,
                year_number=1
            )

            Fee.objects.create(programme_year=year1, label="Inscription", amount=410000, due_month="Octobre")
            Fee.objects.create(programme_year=year1, label="Janvier", amount=200000, due_month="Janvier")
            Fee.objects.create(programme_year=year1, label="Mars", amount=200000, due_month="Mars")

            # ===== Année 2 : 1 200 000 =====
            year2 = ProgrammeYear.objects.create(
                programme=programme,
                year_number=2
            )

            Fee.objects.create(programme_year=year2, label="Inscription", amount=600000, due_month="Octobre")
            Fee.objects.create(programme_year=year2, label="Janvier", amount=300000, due_month="Janvier")
            Fee.objects.create(programme_year=year2, label="Mars", amount=300000, due_month="Mars")

        self.stdout.write(
            self.style.SUCCESS("✅ Seed académique ESFE 2025-2026 terminé proprement.")
        )