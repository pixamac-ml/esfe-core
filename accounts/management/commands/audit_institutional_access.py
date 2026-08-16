"""Report and optionally repair position/group inconsistencies."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from accounts.position_registry import get_position_definition
from accounts.services.institutional_access import (
    compatibility_role_for_position,
    ensure_canonical_groups,
    synchronize_user_position_groups,
)


class Command(BaseCommand):
    help = "Audite les positions institutionnelles et synchronise les groupes canoniques."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Applique la synchronisation. Sans cette option, la commande est en lecture seule.",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        apply_changes = options["apply"]
        if apply_changes:
            ensure_canonical_groups()

        inconsistent = 0
        unassigned = 0
        for user in User.objects.select_related("profile", "institutional_profile").prefetch_related("groups").order_by("username"):
            profile = getattr(user, "profile", None)
            position = getattr(profile, "position", "") if profile else ""
            definition = get_position_definition(position)
            if not definition:
                if user.is_staff:
                    unassigned += 1
                    self.stdout.write(self.style.WARNING(f"SANS POSITION : {user.username}"))
                continue

            expected_group = definition.default_group
            expected_role = compatibility_role_for_position(position)
            groups = set(user.groups.values_list("name", flat=True))
            role_is_valid = getattr(profile, "role", "") == expected_role
            group_is_valid = expected_group in groups
            branch_is_valid = not definition.branch_required or bool(getattr(profile, "branch_id", None))
            if role_is_valid and group_is_valid and branch_is_valid:
                continue

            inconsistent += 1
            self.stdout.write(
                f"INCOHERENT : {user.username} | position={position} | "
                f"groupe attendu={expected_group} | role attendu={expected_role or '<vide>'}"
            )
            if apply_changes:
                synchronize_user_position_groups(user, position=position)
                if profile.role != expected_role:
                    profile.role = expected_role
                    profile.save(update_fields=["role", "updated_at"])

        if not apply_changes and inconsistent:
            raise CommandError(
                f"{inconsistent} compte(s) incohérent(s) détecté(s). Relancez avec --apply après revue."
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Audit terminé : {inconsistent} incohérence(s), {unassigned} compte(s) staff sans position."
            )
        )
