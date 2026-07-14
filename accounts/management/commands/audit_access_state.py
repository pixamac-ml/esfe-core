import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.access import get_user_position
from accounts.access_context import build_access_context
from accounts.position_registry import (
    LEGACY_POSITION_ALIASES,
    get_position_definition,
    normalize_position,
)
from accounts.shadow_access import compare_access_classification


class Command(BaseCommand):
    help = "Audite les positions et portées SYSTEM sans inventer d'affectation."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="N'écrit aucune correction.")
        parser.add_argument("--apply", action="store_true", help="Applique uniquement les alias déterministes.")
        parser.add_argument("--json", action="store_true", dest="as_json", help="Produit une sortie JSON.")

    def handle(self, *args, **options):
        if options["dry_run"] and options["apply"]:
            raise CommandError("--dry-run et --apply sont incompatibles.")

        apply_changes = options["apply"]
        rows = []
        counters = {"users": 0, "valid": 0, "ambiguous": 0, "invalid": 0, "fixable": 0, "fixed": 0}
        users = get_user_model().objects.select_related("profile", "profile__branch").order_by("pk")

        with transaction.atomic():
            for user in users.iterator():
                counters["users"] += 1
                profile = getattr(user, "profile", None)
                raw_position = str(getattr(profile, "position", "") or "").strip().lower()
                normalized = normalize_position(raw_position)
                definition = get_position_definition(normalized)
                issues = []
                status = "valid"

                if not raw_position:
                    inferred = get_user_position(user)
                    if inferred:
                        status = "ambiguous"
                        issues.append("legacy_position_without_official_assignment")
                elif not definition:
                    status = "invalid"
                    issues.append("unknown_position")
                else:
                    if definition.branch_required and not profile.branch_id:
                        status = "invalid"
                        issues.append("branch_required")
                    if not definition.branch_required and profile.branch_id:
                        status = "invalid"
                        issues.append("branch_forbidden_for_global_scope")

                fixable = raw_position in LEGACY_POSITION_ALIASES
                if fixable:
                    counters["fixable"] += 1
                    issues.append("deterministic_alias")
                    if apply_changes:
                        profile.position = normalized
                        profile.save(update_fields=["position", "updated_at"])
                        raw_position = normalized
                        counters["fixed"] += 1

                counters[status] += 1
                context = build_access_context(user)
                divergence = compare_access_classification(user, context=context)
                if issues or divergence:
                    rows.append({
                        "user_id": user.pk,
                        "status": status,
                        "position": raw_position or None,
                        "issues": issues,
                        "shadow_divergence": divergence,
                    })

            if not apply_changes:
                transaction.set_rollback(True)

        payload = {"mode": "apply" if apply_changes else "dry-run", "summary": counters, "accounts": rows}
        if options["as_json"]:
            self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
            return

        self.stdout.write(self.style.SUCCESS(f"Audit terminé ({payload['mode']})"))
        for key, value in counters.items():
            self.stdout.write(f"{key}: {value}")
        for row in rows:
            self.stdout.write(f"user_id={row['user_id']} status={row['status']} issues={','.join(row['issues']) or '-'}")
