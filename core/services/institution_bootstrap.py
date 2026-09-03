"""Bootstrap déterministe des référentiels institutionnels contrôlés."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.apps import apps
from django.core.management import CommandError
from django.db import transaction


ALLOWED_BOOTSTRAP_APPS = {"core", "branches", "formations", "academics"}
REFERENCE_KEY = "$ref"


@dataclass(frozen=True)
class BootstrapSummary:
    created: int
    updated: int
    references: int


def load_bootstrap_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CommandError(f"Fichier de bootstrap introuvable : {path}") from exc
    except json.JSONDecodeError as exc:
        raise CommandError(f"JSON de bootstrap invalide : {exc}") from exc

    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise CommandError("Le manifeste doit être un objet JSON de version 1.")
    objects = payload.get("objects")
    if not isinstance(objects, list):
        raise CommandError("Le manifeste doit contenir une liste 'objects'.")
    return payload


def _resolve_value(value: Any, references: dict[str, Any]) -> Any:
    if isinstance(value, dict) and set(value) == {REFERENCE_KEY}:
        reference = value[REFERENCE_KEY]
        if not isinstance(reference, str) or reference not in references:
            raise CommandError(f"Référence de bootstrap inconnue : {reference!r}")
        return references[reference]
    if isinstance(value, list):
        return [_resolve_value(item, references) for item in value]
    if isinstance(value, dict):
        return {key: _resolve_value(item, references) for key, item in value.items()}
    return value


def _model_from_label(label: Any):
    if not isinstance(label, str) or "." not in label:
        raise CommandError(
            "Chaque objet de bootstrap doit fournir un model 'app_label.ModelName'."
        )
    app_label, model_name = label.split(".", 1)
    if app_label not in ALLOWED_BOOTSTRAP_APPS:
        raise CommandError(f"Modèle de bootstrap interdit : {label}")
    try:
        model = apps.get_model(app_label, model_name)
    except LookupError as exc:
        raise CommandError(f"Modèle de bootstrap inconnu : {label}") from exc
    if not model._meta.managed:
        raise CommandError(f"Modèle non géré interdit dans le bootstrap : {label}")
    return model


def _validate_field_mapping(model, mapping: Any, mapping_name: str) -> dict[str, Any]:
    if not isinstance(mapping, dict):
        raise CommandError(f"{mapping_name} doit être un objet pour {model._meta.label}.")
    validated: dict[str, Any] = {}
    for field_name, value in mapping.items():
        try:
            field = model._meta.get_field(field_name)
        except Exception as exc:
            raise CommandError(
                f"Champ de bootstrap inconnu {model._meta.label}.{field_name}."
            ) from exc
        if field.primary_key or field.many_to_many:
            raise CommandError(
                f"Champ non autorisé dans {mapping_name} : {model._meta.label}.{field_name}."
            )
        validated[field_name] = value
    return validated


def apply_bootstrap_manifest(
    payload: dict[str, Any], *, dry_run: bool = False
) -> BootstrapSummary:
    """Applique un manifeste d'upsert, avec références explicites et transaction."""

    created = 0
    updated = 0
    references: dict[str, Any] = {}
    declared_references: set[str] = set()

    with transaction.atomic():
        for index, specification in enumerate(payload["objects"], start=1):
            if not isinstance(specification, dict):
                raise CommandError(f"Objet #{index} invalide dans le manifeste.")

            model = _model_from_label(specification.get("model"))
            lookup = _validate_field_mapping(model, specification.get("lookup"), "lookup")
            fields = _validate_field_mapping(model, specification.get("fields", {}), "fields")
            reference_name = specification.get("id")
            if reference_name is not None:
                if (
                    not isinstance(reference_name, str)
                    or not reference_name
                    or reference_name in declared_references
                ):
                    raise CommandError(f"Identifiant de référence invalide pour l'objet #{index}.")
                declared_references.add(reference_name)

            resolved_lookup = _resolve_value(lookup, references)
            resolved_fields = _resolve_value(fields, references)
            if not resolved_lookup:
                raise CommandError(f"Lookup vide interdit pour {model._meta.label}.")

            instance, was_created = model._default_manager.update_or_create(
                defaults=resolved_fields,
                **resolved_lookup,
            )
            created += int(was_created)
            updated += int(not was_created)
            if reference_name:
                references[reference_name] = instance

        if dry_run:
            transaction.set_rollback(True)

    return BootstrapSummary(created=created, updated=updated, references=len(references))
