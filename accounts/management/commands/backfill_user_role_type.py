from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from students.models import Student

from accounts.access import get_user_groups, get_user_role
from accounts.models import Profile


User = get_user_model()


class Command(BaseCommand):
    help = "Complète role et user_type des utilisateurs existants sans écraser les profils valides."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Affiche le plan sans écrire en base.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        updated_profiles = 0
        filled_role = 0
        filled_user_type = 0

        users = User.objects.all().prefetch_related("groups")

        for user in users:
            profile, _ = Profile.objects.get_or_create(user=user)
            changed_fields = []

            # Ne jamais auto-assigner la position (exigence métier).
            username = str(getattr(user, "username", "")).lower()
            is_student_like = bool(
                username.startswith("etu_esfe")
                or Student.objects.filter(user=user).exists()
            )
            has_groups = bool(get_user_groups(user))

            if not profile.user_type:
                if is_student_like:
                    profile.user_type = "staff"
                elif has_groups:
                    profile.user_type = "staff"
                else:
                    profile.user_type = "public"

                changed_fields.append("user_type")
                filled_user_type += 1

            if not profile.role:
                assigned_role = self._resolve_legacy_profile_role(user, is_student_like=is_student_like)
                if assigned_role:
                    profile.role = assigned_role
                    changed_fields.append("role")
                    filled_role += 1

            if changed_fields:
                updated_profiles += 1
                if not dry_run:
                    if "updated_at" not in changed_fields:
                        changed_fields.append("updated_at")
                    profile.save(update_fields=changed_fields)

        mode = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(
            f"{mode}Utilisateurs traités: {users.count()} | profils mis à jour: {updated_profiles} | role complétés: {filled_role} | user_type complétés: {filled_user_type}"
        ))

    def _resolve_legacy_profile_role(self, user, *, is_student_like):
        if is_student_like:
            return "student"

        groups = set(get_user_groups(user))
        canonical_role = get_user_role(user)

        if canonical_role == "super_admin":
            return "superadmin"

        if canonical_role == "directeur_etudes":
            return "executive"

        if canonical_role == "teacher":
            return "teacher"

        if canonical_role == "student":
            return "student"

        if canonical_role == "staff_admin":
            # Mapping déterministe et compatible avec ROLE_CHOICES existants.
            if groups.intersection({"finance_agents", "finance"}):
                return "finance"
            if groups.intersection({"admissions_managers", "admissions", "gestionnaire", "manager"}):
                return "admissions"

        return None

