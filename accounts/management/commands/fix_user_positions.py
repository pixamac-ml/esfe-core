from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.access import get_user_position
from accounts.models import Profile

User = get_user_model()


class Command(BaseCommand):
    help = "Assigne automatiquement profile.position aux utilisateurs existants quand elle est detectable."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Affiche les changements sans ecriture.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        updated = 0
        unresolved = 0

        for user in User.objects.all().prefetch_related("groups"):
            profile, _ = Profile.objects.get_or_create(user=user)
            if profile.position:
                continue

            position = get_user_position(user)
            if not position:
                unresolved += 1
                self.stdout.write(
                    self.style.WARNING(f"Position introuvable pour {user.username}")
                )
                continue

            updated += 1
            self.stdout.write(f"{user.username}: position -> {position}")

            if not dry_run:
                profile.position = position
                profile.save(update_fields=["position", "updated_at"])

        prefix = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Positions mises a jour: {updated} | non resolues: {unresolved}"
            )
        )
