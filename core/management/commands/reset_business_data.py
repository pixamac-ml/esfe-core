from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.services.business_data_reset import (
    assert_migrations_current,
    assert_safe_local_development_database,
    reset_business_data,
)


def _pg_restore_binary() -> str | None:
    discovered = shutil.which("pg_restore")
    if discovered:
        return discovered
    windows_default = Path(r"C:\Program Files\PostgreSQL\18\bin\pg_restore.exe")
    return str(windows_default) if windows_default.exists() else None


def _validate_backup(path: Path, database_name: str) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise CommandError("Backup absent ou vide : " + str(path))
    pg_restore = _pg_restore_binary()
    if not pg_restore:
        raise CommandError("pg_restore introuvable : impossible de vérifier le backup.")

    completed = subprocess.run(
        [pg_restore, "--list", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode:
        raise CommandError("Backup PostgreSQL illisible : " + completed.stderr.strip())
    if f"dbname: {database_name}" not in completed.stdout:
        raise CommandError("Le backup ne correspond pas à la base PostgreSQL ciblée.")


class Command(BaseCommand):
    help = "Purge contrôlée des données métier d'un PostgreSQL local de développement."

    def add_arguments(self, parser):
        parser.add_argument(
            "--preserve-user",
            action="append",
            default=[],
            metavar="USERNAME",
            help="Compte à conserver ; répéter l'option pour chaque compte protégé.",
        )
        parser.add_argument(
            "--backup-file",
            type=Path,
            help="Archive pg_dump complète, obligatoire hors --dry-run.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Affiche la base ciblée et vérifie les protections sans écrire.",
        )
        parser.add_argument(
            "--yes-really-reset",
            action="store_true",
            help="Confirmation explicite pour une automatisation locale contrôlée.",
        )

    def handle(self, *args, **options):
        identity = assert_safe_local_development_database()
        assert_migrations_current()
        self.stdout.write(
            self.style.WARNING(
                "Base ciblée : {name} sur {host}:{port} ({engine})".format(**identity)
            )
        )

        preserved = options["preserve_user"]
        if not preserved:
            raise CommandError("--preserve-user est obligatoire.")

        if options["dry_run"]:
            self.stdout.write("Dry-run validé : aucune donnée n'a été modifiée.")
            return

        backup_path = options["backup_file"]
        if backup_path is None:
            raise CommandError("--backup-file est obligatoire avant toute purge.")
        _validate_backup(backup_path.resolve(), identity["name"])

        if not options["yes_really_reset"]:
            expected = f"RESET {identity['name']}"
            try:
                confirmation = input(f"Tapez exactement '{expected}' pour confirmer : ").strip()
            except EOFError as exc:
                raise CommandError("Confirmation interactive absente.") from exc
            if confirmation != expected:
                raise CommandError("Confirmation incorrecte : aucune donnée supprimée.")

        summary = reset_business_data(preserve_usernames=preserved)
        self.stdout.write(self.style.SUCCESS("Reset métier terminé."))
        self.stdout.write("Comptes conservés : " + ", ".join(summary.protected_usernames))
        self.stdout.write(
            "Liens d'annexe retirés des profils conservés : "
            + str(summary.protected_branch_links_cleared)
        )
        self.stdout.write("Objets supprimés : " + str(summary.deleted_total))
        for label, count in summary.deleted_by_model.items():
            self.stdout.write(f"  - {label}: {count}")
