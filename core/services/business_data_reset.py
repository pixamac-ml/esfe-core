"""Purge contrôlée des données métier d'un environnement local ESFE.

Ce module ne touche ni aux migrations, ni aux permissions, ni aux groupes Django.
Les comptes explicitement protégés restent en place avec leurs profils de rôle.
"""

from __future__ import annotations

import os
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Iterable

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import CommandError
from django.db import connection, transaction
from django.db.models.deletion import CASCADE, DO_NOTHING, PROTECT, RESTRICT
from django.db.migrations.executor import MigrationExecutor


# Les applications fonctionnelles dont les données sont réinitialisables. La
# liste est volontairement explicite : une nouvelle application n'est jamais
# purgée implicitement par une commande destructive.
RESET_APP_LABELS = {
    "academic_cycle",
    "academics",
    "accounts",
    "admissions",
    "axes",
    "blog",
    "branches",
    "community",
    "core",
    "coupons",
    "formations",
    "inscriptions",
    "marketing",
    "memoires",
    "news",
    "notifier",
    "payments",
    "portal",
    "secretary",
    "sessions",
    "shop",
    "students",
    "superadmin",
}

# Infrastructure Django à conserver afin que l'administration, les permissions
# et les migrations restent opérationnelles après le reset.
EXCLUDED_MODEL_LABELS = {
    "accounts.profile",
    "accounts.institutionalprofile",
    "accounts.publiccommunityprofile",
    "auth.user",
}

PRESERVED_ACCOUNT_MODEL_LABELS = (
    "accounts.profile",
    "accounts.institutionalprofile",
    "accounts.publiccommunityprofile",
)

LOCAL_POSTGRES_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}
PRODUCTION_ENVIRONMENT_VALUES = {"prod", "production", "live"}

# Tables issues d'applications retirées du code mais encore présentes dans le
# schéma local. Elles restent explicitement nommées et seules leurs lignes sont
# supprimées ; la commande ne détruit jamais leur schéma.
LEGACY_BUSINESS_TABLES = (
    "communication_messagereadreceipt",
    "communication_messageattachment",
    "communication_conversationparticipant",
    "communication_conversationmessage",
    "communication_conversation",
    "membership_employment",
    "membership_schoolmembership",
)


@dataclass(frozen=True)
class ResetSummary:
    """Résultat utilisable à la fois par la commande et par les tests."""

    protected_usernames: tuple[str, ...]
    deleted_by_model: dict[str, int]
    protected_branch_links_cleared: int

    @property
    def deleted_total(self) -> int:
        return sum(self.deleted_by_model.values())


def database_identity() -> dict[str, str]:
    """Retourne une identité non sensible de la base configurée."""

    config = connection.settings_dict
    return {
        "engine": str(config.get("ENGINE", "")),
        "name": str(config.get("NAME", "")),
        "host": str(config.get("HOST") or "<default>"),
        "port": str(config.get("PORT") or "<default>"),
        "vendor": connection.vendor,
    }


def assert_safe_local_development_database() -> dict[str, str]:
    """Refuse toute purge hors d'un PostgreSQL local explicitement en DEBUG."""

    identity = database_identity()
    environment = (
        os.getenv("DJANGO_ENV")
        or os.getenv("ENVIRONMENT")
        or os.getenv("DEPLOYMENT_ENV")
        or ""
    ).strip().lower()
    name = identity["name"].lower()
    host = identity["host"].lower()

    if not settings.DEBUG:
        raise CommandError("Reset refusé : DEBUG doit être activé.")
    if environment in PRODUCTION_ENVIRONMENT_VALUES:
        raise CommandError("Reset refusé : environnement de production détecté.")
    if connection.vendor != "postgresql":
        raise CommandError("Reset refusé : seul PostgreSQL local est autorisé.")
    if host not in LOCAL_POSTGRES_HOSTS:
        raise CommandError(
            "Reset refusé : l'hôte PostgreSQL doit être localhost, 127.0.0.1 ou ::1."
        )
    if "prod" in name or "production" in name:
        raise CommandError("Reset refusé : le nom de base ressemble à une production.")

    return identity


def assert_migrations_current() -> None:
    """Évite une purge partielle lorsque le code et le schéma divergent."""

    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    if plan:
        pending = ", ".join(
            f"{migration.app_label}.{migration.name}" for migration, _backwards in plan
        )
        raise CommandError(
            "Reset refusé : migrations non appliquées. Exécutez d'abord 'python manage.py migrate' "
            f"({pending})."
        )


def get_reset_models() -> list[type]:
    """Retourne exclusivement les modèles métier explicitement réinitialisables."""

    models = []
    for model in apps.get_models():
        opts = model._meta
        if not opts.managed or opts.proxy or opts.auto_created:
            continue
        if opts.app_label not in RESET_APP_LABELS:
            continue
        if opts.label_lower in EXCLUDED_MODEL_LABELS:
            continue
        models.append(model)
    return models


def deletion_order(models: Iterable[type]) -> list[type]:
    """Classe les modèles des enfants vers leurs parents FK/O2O.

    Django traite ensuite les relations CASCADE et M2M pendant chaque delete.
    Les rares cycles restants sont supprimés dans un ordre stable à l'intérieur
    de la même transaction ; ils sont signalés par les contraintes Django si un
    nouveau lien PROTECT impose une règle supplémentaire.
    """

    model_set = set(models)
    outgoing: dict[type, set[type]] = defaultdict(set)
    indegree: dict[type, int] = {model: 0 for model in model_set}

    for child in model_set:
        for field in child._meta.fields:
            remote = getattr(field.remote_field, "model", None)
            on_delete = getattr(field.remote_field, "on_delete", None)
            # CASCADE doit également être ordonné enfant -> parent : un enfant
            # collecté en cascade peut lui-même être protégé par un troisième
            # modèle (ex. UE -> EC <- AcademicScheduleEvent). SET_NULL et
            # SET_DEFAULT restent exclus afin d'éviter les cycles artificiels
            # comme Topic.accepted_answer.
            requires_child_first = on_delete in {CASCADE, PROTECT, RESTRICT, DO_NOTHING}
            if (
                requires_child_first
                and remote in model_set
                and remote is not child
                and remote not in outgoing[child]
            ):
                outgoing[child].add(remote)
                indegree[remote] += 1

    ready = deque(
        sorted(
            (model for model, degree in indegree.items() if degree == 0),
            key=lambda model: model._meta.label_lower,
        )
    )
    ordered: list[type] = []
    while ready:
        model = ready.popleft()
        ordered.append(model)
        for parent in sorted(outgoing[model], key=lambda item: item._meta.label_lower):
            indegree[parent] -= 1
            if indegree[parent] == 0:
                ready.append(parent)

    if len(ordered) != len(model_set):
        remaining = sorted(model_set.difference(ordered), key=lambda model: model._meta.label_lower)
        ordered.extend(remaining)

    return ordered


def _protected_users(usernames: Iterable[str]):
    usernames = tuple(
        dict.fromkeys(username.strip() for username in usernames if username.strip())
    )
    if not usernames:
        raise CommandError("Indiquez au moins un compte avec --preserve-user.")

    user_model = get_user_model()
    users = list(
        user_model.objects.select_for_update()
        .filter(username__in=usernames)
        .order_by("username")
    )
    found_usernames = {user.username for user in users}
    missing = sorted(set(usernames).difference(found_usernames))
    if missing:
        raise CommandError("Compte(s) à conserver introuvable(s) : " + ", ".join(missing))
    if not any(user.is_superuser for user in users):
        raise CommandError("Au moins un superuser doit être explicitement conservé.")
    if any(not user.is_active or not user.has_usable_password() for user in users):
        raise CommandError(
            "Les comptes conservés doivent être actifs et avoir un mot de passe utilisable."
        )
    return users


def _clear_preserved_profile_branch_links(user_ids: list[int]) -> int:
    """Détache les profils protégés d'annexes appelées à être supprimées."""

    cleared = 0
    for label in ("accounts.profile", "accounts.institutionalprofile"):
        model = apps.get_model(label)
        queryset = model.objects.filter(user_id__in=user_ids, branch__isnull=False)
        count = queryset.count()
        if count:
            queryset.update(branch=None)
            cleared += count
    return cleared


def _delete_non_preserved_account_profiles(
    user_ids: list[int], deleted: dict[str, int]
) -> None:
    for label in PRESERVED_ACCOUNT_MODEL_LABELS:
        model = apps.get_model(label)
        count = model.objects.exclude(user_id__in=user_ids).count()
        if count:
            model.objects.exclude(user_id__in=user_ids).delete()
            deleted[model._meta.label] = count


def _public_table_names() -> set[str]:
    with connection.cursor() as cursor:
        return set(connection.introspection.table_names(cursor))


def _unmapped_table_names() -> set[str]:
    mapped = {
        model._meta.db_table
        for model in apps.get_models(include_auto_created=True)
        if model._meta.managed
    }
    mapped.add("django_migrations")
    return _public_table_names().difference(mapped)


def _delete_legacy_business_rows(deleted: dict[str, int]) -> None:
    existing_tables = _public_table_names()
    with connection.cursor() as cursor:
        for table_name in LEGACY_BUSINESS_TABLES:
            if table_name not in existing_tables:
                continue
            quoted_table = connection.ops.quote_name(table_name)
            cursor.execute(f"SELECT COUNT(*) FROM {quoted_table}")
            count = cursor.fetchone()[0]
            if count:
                cursor.execute(f"DELETE FROM {quoted_table}")
                deleted[f"legacy.{table_name}"] = count


def _remaining_unmapped_rows() -> dict[str, int]:
    remaining: dict[str, int] = {}
    with connection.cursor() as cursor:
        for table_name in sorted(_unmapped_table_names()):
            quoted_table = connection.ops.quote_name(table_name)
            cursor.execute(f"SELECT COUNT(*) FROM {quoted_table}")
            count = cursor.fetchone()[0]
            if count:
                remaining[f"legacy.{table_name}"] = count
    return remaining


def remaining_business_data(user_ids: Iterable[int]) -> dict[str, int]:
    """Compte ce qui devrait être vide après purge, sans compter le socle Django."""

    remaining = {
        model._meta.label: model._default_manager.count()
        for model in get_reset_models()
        if model._default_manager.exists()
    }
    protected_ids = list(user_ids)
    for label in PRESERVED_ACCOUNT_MODEL_LABELS:
        model = apps.get_model(label)
        count = model.objects.exclude(user_id__in=protected_ids).count()
        if count:
            remaining[model._meta.label] = count

    user_model = get_user_model()
    user_count = user_model.objects.exclude(pk__in=protected_ids).count()
    if user_count:
        remaining[user_model._meta.label] = user_count
    remaining.update(_remaining_unmapped_rows())
    return remaining


def reset_business_data(*, preserve_usernames: Iterable[str]) -> ResetSummary:
    """Supprime les données métier dans une transaction PostgreSQL atomique."""

    deleted: dict[str, int] = {}
    with transaction.atomic():
        # Évite deux resets concurrents sur la même base locale.
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    ["esfe:reset-business-data"],
                )

        protected_users = _protected_users(preserve_usernames)
        protected_user_ids = [user.pk for user in protected_users]
        _delete_legacy_business_rows(deleted)
        cleared_links = _clear_preserved_profile_branch_links(protected_user_ids)
        _delete_non_preserved_account_profiles(protected_user_ids, deleted)

        for model in deletion_order(get_reset_models()):
            count = model._default_manager.count()
            if not count:
                continue
            model._default_manager.all().delete()
            deleted[model._meta.label] = count

        user_model = get_user_model()
        user_count = user_model.objects.exclude(pk__in=protected_user_ids).count()
        if user_count:
            user_model.objects.exclude(pk__in=protected_user_ids).delete()
            deleted[user_model._meta.label] = user_count

        remaining = remaining_business_data(protected_user_ids)
        if remaining:
            details = ", ".join(f"{label}={count}" for label, count in sorted(remaining.items()))
            raise CommandError("Reset annulé : données métier restantes : " + details)

    return ResetSummary(
        protected_usernames=tuple(user.username for user in protected_users),
        deleted_by_model=dict(sorted(deleted.items())),
        protected_branch_links_cleared=cleared_links,
    )
