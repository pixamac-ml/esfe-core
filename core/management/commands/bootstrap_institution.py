from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from core.services.institution_bootstrap import apply_bootstrap_manifest, load_bootstrap_manifest


class Command(BaseCommand):
    help = "Bootstrap idempotent des référentiels institutionnels depuis un manifeste contrôlé."

    def add_arguments(self, parser):
        parser.add_argument(
            "--data-file",
            type=Path,
            default=Path(settings.BASE_DIR) / "bootstrap" / "institution.json",
            help="Manifeste JSON versionné à appliquer.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Valide le manifeste et annule la transaction avant écriture.",
        )

    def handle(self, *args, **options):
        path = options["data_file"].resolve()
        payload = load_bootstrap_manifest(path)
        summary = apply_bootstrap_manifest(payload, dry_run=options["dry_run"])
        mode = " (dry-run)" if options["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS("Bootstrap institutionnel terminé" + mode + "."))
        self.stdout.write(
            f"Créés : {summary.created}; mis à jour : {summary.updated}; références : {summary.references}."
        )
