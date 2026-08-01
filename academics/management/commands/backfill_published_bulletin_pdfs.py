from django.core.management.base import BaseCommand

from academics.models import AcademicBulletin
from academics.services.documents import backfill_published_bulletin


class Command(BaseCommand):
    help = "Fige les snapshots historiques et cree les PDF manquants des bulletins publies."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Applique le backfill. Sans cette option, affiche uniquement le nombre de candidats.",
        )

    def handle(self, *args, **options):
        bulletins = AcademicBulletin.objects.filter(
            status=AcademicBulletin.STATUS_PUBLISHED,
        ).order_by("pk")
        candidates = [
            bulletin
            for bulletin in bulletins
            if (bulletin.snapshot or {}).get("version") != 2 or not bulletin.pdf_file
        ]
        self.stdout.write(f"{len(candidates)} bulletin(s) publie(s) a figer.")
        if not options["apply"]:
            self.stdout.write("Relancer avec --apply pour appliquer les changements.")
            return

        updated = 0
        errors = 0
        for bulletin in candidates:
            try:
                frozen, snapshot_updated, pdf_created = backfill_published_bulletin(bulletin)
            except Exception as exc:
                errors += 1
                self.stderr.write(self.style.ERROR(f"{bulletin.reference}: {exc}"))
                continue
            updated += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"{frozen.reference}: snapshot={'oui' if snapshot_updated else 'deja'}; "
                    f"pdf={'cree' if pdf_created else 'deja'}"
                )
            )

        self.stdout.write(self.style.SUCCESS(f"Termine: {updated} traite(s), {errors} erreur(s)."))
