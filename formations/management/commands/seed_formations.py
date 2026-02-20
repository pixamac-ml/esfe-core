from django.core.management.base import BaseCommand
from formations.models import (
    Cycle, Diploma, Filiere,
    Programme, ProgrammeYear, Fee
)


class Command(BaseCommand):
    help = "Seed formations propre (Cycle Licence + Cycle Master)"

    def handle(self, *args, **kwargs):

        # ======================================================
        # RÉCUPÉRATION DES CYCLES EXISTANTS
        # ======================================================

        try:
            licence = Cycle.objects.get(slug="cycle-licence")
            master = Cycle.objects.get(slug="cycle-master")
        except Cycle.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                "❌ Les cycles 'Cycle Licence' ou 'Cycle Master' n'existent pas."
            ))
            return

        diploma_sup, _ = Diploma.objects.get_or_create(
            name="Diplôme Supérieur",
            defaults={"level": "superieur"}
        )

        filiere_sante, _ = Filiere.objects.get_or_create(
            name="Sciences de la santé"
        )

        # ======================================================
        # LICENCE — INFIRMIER D'ÉTAT
        # Structure temporaire standardisée :
        # 130 000 + 140 000 + 140 000 = 410 000
        # ======================================================

        programme, created = Programme.objects.get_or_create(
            title="Infirmier d’État",
            defaults={
                "cycle": licence,
                "filiere": filiere_sante,
                "diploma_awarded": diploma_sup,
                "duration_years": 3,
                "short_description": "Formation professionnelle en soins infirmiers et gestion clinique.",
                "description": """
La formation d’Infirmier d’État prépare des professionnels capables
d’assurer la prise en charge globale des patients dans les structures sanitaires.
""",
                "learning_outcomes": """
Maîtrise des soins infirmiers généraux
Gestion des urgences médicales
Surveillance clinique avancée
Éducation thérapeutique des patients
Travail en équipe pluridisciplinaire
                """,
                "career_opportunities": """
Hôpitaux publics
Cliniques privées
Centres de santé communautaires
ONG médicales
Institutions internationales
                """,
                "is_active": True,
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f"✔ Créé : {programme.title}"))
        else:
            self.stdout.write(self.style.WARNING(f"⚠ Mise à jour : {programme.title}"))
            programme.years.all().delete()  # Nettoyage propre avant recréation

        for year_number in range(1, programme.duration_years + 1):
            year = ProgrammeYear.objects.create(
                programme=programme,
                year_number=year_number
            )

            Fee.objects.create(
                programme_year=year,
                label="Inscription",
                amount=130000,
                due_month="Octobre"
            )

            Fee.objects.create(
                programme_year=year,
                label="Janvier",
                amount=140000,
                due_month="Janvier"
            )

            Fee.objects.create(
                programme_year=year,
                label="Mars",
                amount=140000,
                due_month="Mars"
            )

        # ======================================================
        # MASTER — SANTÉ COMMUNAUTAIRE
        # ======================================================

        programme_master, created = Programme.objects.get_or_create(
            title="Santé communautaire",
            defaults={
                "cycle": master,
                "filiere": filiere_sante,
                "diploma_awarded": diploma_sup,
                "duration_years": 2,
                "short_description": "Formation stratégique en gestion des systèmes de santé.",
                "description": """
Le Master en Santé communautaire forme des cadres capables
de concevoir, piloter et évaluer des programmes de santé publique.
""",
                "learning_outcomes": """
Conception de politiques sanitaires
Évaluation des programmes publics
Analyse statistique avancée
Gestion stratégique des systèmes de santé
Leadership institutionnel
                """,
                "career_opportunities": """
Ministère de la Santé
ONG internationales
Instituts de recherche
Organisations de santé publique
Consulting en santé
                """,
                "is_active": True,
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f"✔ Créé : {programme_master.title}"))
        else:
            self.stdout.write(self.style.WARNING(f"⚠ Mise à jour : {programme_master.title}"))
            programme_master.years.all().delete()

        # 1ère année
        year1 = ProgrammeYear.objects.create(
            programme=programme_master,
            year_number=1
        )

        Fee.objects.create(programme_year=year1, label="Inscription", amount=410000, due_month="Octobre")
        Fee.objects.create(programme_year=year1, label="Janvier", amount=200000, due_month="Janvier")
        Fee.objects.create(programme_year=year1, label="Mars", amount=200000, due_month="Mars")

        # 2ème année
        year2 = ProgrammeYear.objects.create(
            programme=programme_master,
            year_number=2
        )

        Fee.objects.create(programme_year=year2, label="Inscription", amount=600000, due_month="Octobre")
        Fee.objects.create(programme_year=year2, label="Janvier", amount=300000, due_month="Janvier")
        Fee.objects.create(programme_year=year2, label="Mars", amount=300000, due_month="Mars")

        self.stdout.write(self.style.SUCCESS("🎓 Seed terminé proprement."))