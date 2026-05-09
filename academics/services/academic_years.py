import re

from academics.models import AcademicYear


def canonicalize_academic_year_name(value):
    raw_value = str(value or "").strip()
    if not raw_value:
        return ""

    compact_value = raw_value.replace(" ", "")
    if re.fullmatch(r"\d{4}[-/]\d{4}", compact_value):
        return compact_value.replace("/", "-")

    return raw_value


def get_current_academic_year():
    return AcademicYear.objects.filter(is_active=True).first()


def get_current_academic_year_name():
    current_year = get_current_academic_year()
    return current_year.name if current_year else ""


def resolve_academic_year_reference(value):
    academic_year_name = canonicalize_academic_year_name(value)
    if not academic_year_name:
        return {
            "status": "manual_required_missing_year",
            "reason": "missing_academic_year",
            "academic_year": None,
            "academic_year_name": "",
            "warnings": [],
        }

    exact_match = AcademicYear.objects.filter(name=academic_year_name).first()
    if exact_match:
        return {
            "status": "resolved",
            "reason": None,
            "academic_year": exact_match,
            "academic_year_name": exact_match.name,
            "warnings": [],
        }

    for candidate in AcademicYear.objects.all():
        if canonicalize_academic_year_name(candidate.name) == academic_year_name:
            return {
                "status": "resolved",
                "reason": None,
                "academic_year": candidate,
                "academic_year_name": candidate.name,
                "warnings": ["normalized_academic_year_lookup"],
            }

    return {
        "status": "manual_required_missing_year",
        "reason": "academic_year_not_found",
        "academic_year": None,
        "academic_year_name": academic_year_name,
        "warnings": [],
    }
