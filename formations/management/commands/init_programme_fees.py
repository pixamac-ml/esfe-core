from django.core.management.base import BaseCommand
from formations.models import Programme, ProgrammeYear, Fee


class Command(BaseCommand):
    help = "Initialise automatiquement les années et frais pour les programmes sans configuration"

    def handle(self, *args, **options):
        created_programmes = 0

        for programme in Programme.objects.all():

            # Vérifie s’il existe déjà des années
            if programme.years.exists():
                continue

            self.stdout.write(
                self.style.WARNING(
                    f"⚠ Initialisation des frais pour : {programme.title}"
                )
            )

            # Création des années
            for year in range(1, programme.duration_years + 1):
                programme_year = ProgrammeYear.objects.create(
                    programme=programme,
                    year_number=year
                )

                # Frais par défaut (modifiable après)
                Fee.objects.create(
                    programme_year=programme_year,
                    label="Inscription",
                    amount=50000,
                    due_month="Octobre"
                )

                Fee.objects.create(
                    programme_year=programme_year,
                    label="1ère tranche",
                    amount=150000,
                    due_month="Janvier"
                )

                Fee.objects.create(
                    programme_year=programme_year,
                    label="2ème tranche",
                    amount=150000,
                    due_month="Mars"
                )

            created_programmes += 1

        if created_programmes == 0:
            self.stdout.write(
                self.style.SUCCESS("✅ Tous les programmes ont déjà des frais.")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Frais initialisés pour {created_programmes} programme(s)."
                )
            )
