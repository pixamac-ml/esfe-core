import re

from academics.models import AcademicClass
from academics.services.academic_context_resolver import resolve_academic_year


LEVEL_ORDER = {
    "L1": 10,
    "L2": 20,
    "L3": 30,
    "M1": 40,
    "M2": 50,
}


def normalize_academic_level(level):
    return str(level or "").strip().upper()


def academic_level_sort_key(level):
    normalized = normalize_academic_level(level)
    if normalized in LEVEL_ORDER:
        return LEVEL_ORDER[normalized], normalized

    match = re.match(r"^([A-Z]+)(\d+)$", normalized)
    if match:
        return 100 + int(match.group(2)), normalized

    return 999, normalized


def get_programme_year_number_for_level(level):
    normalized = normalize_academic_level(level)
    match = re.search(r"(\d+)$", normalized)
    if not match:
        return None
    return int(match.group(1))


def get_positioning_fee_for_level(programme, level):
    year_number = get_programme_year_number_for_level(level)
    if not year_number:
        return 0
    return programme.get_inscription_amount_for_year(year_number) or 0


def get_positioning_context(*, candidature):
    year_result = resolve_academic_year(getattr(candidature, "academic_year", None))
    if year_result["status"] != "resolved":
        return {
            "status": year_result["status"],
            "reason": year_result["reason"],
            "academic_year": None,
            "academic_year_name": year_result["academic_year_name"],
            "available_levels": [],
            "available_classes": [],
            "fee_by_level": {},
            "error_message": (
                "L'annee academique de cette candidature ne correspond a aucune annee academique "
                "configuree dans le systeme."
            ),
        }

    classes = list(
        AcademicClass.objects.filter(
            programme=candidature.programme,
            branch=candidature.branch,
            academic_year=year_result["academic_year"],
            is_active=True,
        )
        .select_related("academic_year", "programme", "branch")
        .order_by("level", "name", "id")
    )

    levels = sorted(
        {normalize_academic_level(item.level) for item in classes if normalize_academic_level(item.level)},
        key=academic_level_sort_key,
    )
    fee_by_level = {
        level: get_positioning_fee_for_level(candidature.programme, level)
        for level in levels
    }
    for academic_class in classes:
        academic_class.positioning_fee = fee_by_level.get(normalize_academic_level(academic_class.level), 0)

    error_message = ""
    if not classes:
        error_message = (
            "Aucune classe active compatible n'existe pour ce programme, cette annexe et cette annee academique. "
            "Creez d'abord la classe avant de poursuivre."
        )

    return {
        "status": "ok" if classes else "missing_classes",
        "reason": None if classes else "academic_class_not_found",
        "academic_year": year_result["academic_year"],
        "academic_year_name": year_result["academic_year_name"],
        "available_levels": levels,
        "available_classes": classes,
        "fee_by_level": fee_by_level,
        "error_message": error_message,
    }


def validate_academic_class_for_candidature(*, candidature, academic_class):
    if candidature is None:
        return {"ok": False, "reason": "missing_candidature", "message": "Candidature absente."}

    if academic_class is None:
        return {
            "ok": False,
            "reason": "missing_academic_class",
            "message": "Le positionnement academique est obligatoire avant la creation de l'inscription.",
        }

    context = get_positioning_context(candidature=candidature)
    if context["status"] != "ok":
        return {
            "ok": False,
            "reason": context["reason"],
            "message": context["error_message"],
        }

    if not academic_class.is_active:
        return {
            "ok": False,
            "reason": "inactive_academic_class",
            "message": "La classe selectionnee n'est pas active.",
        }

    if academic_class.programme_id != candidature.programme_id:
        return {
            "ok": False,
            "reason": "programme_mismatch",
            "message": "La classe selectionnee ne correspond pas au programme de la candidature.",
        }

    if academic_class.branch_id != candidature.branch_id:
        return {
            "ok": False,
            "reason": "branch_mismatch",
            "message": "La classe selectionnee ne correspond pas a l'annexe de la candidature.",
        }

    if academic_class.academic_year_id != context["academic_year"].id:
        return {
            "ok": False,
            "reason": "academic_year_mismatch",
            "message": "La classe selectionnee ne correspond pas a l'annee academique de la candidature.",
        }

    return {
        "ok": True,
        "reason": None,
        "message": "",
        "academic_year": context["academic_year"],
    }
