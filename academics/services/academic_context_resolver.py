import logging

from academics.models import AcademicClass
from academics.services.academic_years import resolve_academic_year_reference


logger = logging.getLogger(__name__)


LEGACY_ENTRY_YEAR_TO_LEVEL = {
    1: "L1",
    2: "L2",
    3: "L3",
    4: "M1",
    5: "M2",
}

LICENCE_ENTRY_YEAR_TO_LEVEL = {
    1: "L1",
    2: "L2",
    3: "L3",
}

MASTER_ENTRY_YEAR_TO_LEVEL = {
    1: "M1",
    2: "M2",
}


def _build_result(status, *, reason=None, programme=None, branch=None, cycle=None, academic_year=None, academic_year_name=None, resolved_level=None, academic_class=None, warnings=None):
    return {
        "status": status,
        "reason": reason,
        "programme": programme,
        "branch": branch,
        "cycle": cycle,
        "academic_year": academic_year,
        "academic_year_name": academic_year_name,
        "resolved_level": resolved_level,
        "academic_class": academic_class,
        "warnings": warnings or [],
    }


def _normalize_cycle_name(cycle):
    return str(getattr(cycle, "name", "") or "").strip().lower()


def resolve_academic_year(academic_year_value):
    result = resolve_academic_year_reference(academic_year_value)
    return _build_result(
        result["status"],
        reason=result["reason"],
        academic_year=result["academic_year"],
        academic_year_name=result["academic_year_name"],
        warnings=result["warnings"],
    )


def resolve_level_from_entry_year(programme, entry_year):
    cycle = getattr(programme, "cycle", None)
    cycle_name = _normalize_cycle_name(cycle)

    if entry_year in (None, ""):
        return _build_result(
            "manual_required_ambiguous_level",
            reason="missing_entry_year",
            programme=programme,
            cycle=cycle,
        )

    try:
        normalized_entry_year = int(entry_year)
    except (TypeError, ValueError):
        return _build_result(
            "manual_required_ambiguous_level",
            reason="invalid_entry_year",
            programme=programme,
            cycle=cycle,
        )

    if normalized_entry_year <= 0:
        return _build_result(
            "manual_required_ambiguous_level",
            reason="invalid_entry_year",
            programme=programme,
            cycle=cycle,
        )

    if "master" in cycle_name:
        level = MASTER_ENTRY_YEAR_TO_LEVEL.get(normalized_entry_year)
        if not level and normalized_entry_year in (4, 5):
            level = LEGACY_ENTRY_YEAR_TO_LEVEL.get(normalized_entry_year)
        if not level:
            return _build_result(
                "manual_required_ambiguous_level",
                reason="unsupported_master_entry_year",
                programme=programme,
                cycle=cycle,
            )
        return _build_result(
            "resolved",
            programme=programme,
            cycle=cycle,
            resolved_level=level,
        )

    if "licence" in cycle_name or "license" in cycle_name:
        level = LICENCE_ENTRY_YEAR_TO_LEVEL.get(normalized_entry_year)
        if not level:
            return _build_result(
                "manual_required_ambiguous_level",
                reason="unsupported_licence_entry_year",
                programme=programme,
                cycle=cycle,
            )
        return _build_result(
            "resolved",
            programme=programme,
            cycle=cycle,
            resolved_level=level,
        )

    level = LEGACY_ENTRY_YEAR_TO_LEVEL.get(normalized_entry_year)
    if not level:
        return _build_result(
            "manual_required_ambiguous_level",
            reason="level_not_resolved",
            programme=programme,
            cycle=cycle,
        )

    warnings = []
    duration_years = getattr(programme, "duration_years", None)
    if duration_years and normalized_entry_year > duration_years:
        warnings.append("entry_year_exceeds_programme_duration")

    return _build_result(
        "resolved",
        programme=programme,
        cycle=cycle,
        resolved_level=level,
        warnings=warnings,
    )


def resolve_academic_context(*, candidature, programme=None, branch=None, entry_year=None, academic_year_value=None):
    programme = programme or getattr(candidature, "programme", None)
    branch = branch or getattr(candidature, "branch", None)
    entry_year = entry_year if entry_year is not None else getattr(candidature, "entry_year", None)
    academic_year_value = (
        academic_year_value
        if academic_year_value is not None
        else getattr(candidature, "academic_year", None)
    )

    if candidature is None:
        return _build_result("error_inconsistent_data", reason="missing_candidature")

    if not programme:
        return _build_result("manual_required_missing_programme", reason="missing_programme")

    if not branch:
        return _build_result(
            "manual_required_missing_branch",
            reason="missing_branch",
            programme=programme,
        )

    year_result = resolve_academic_year(academic_year_value)
    if year_result["status"] != "resolved":
        return _build_result(
            year_result["status"],
            reason=year_result["reason"],
            programme=programme,
            branch=branch,
            cycle=getattr(programme, "cycle", None),
            academic_year_name=year_result["academic_year_name"],
            warnings=year_result["warnings"],
        )

    level_result = resolve_level_from_entry_year(programme, entry_year)
    if level_result["status"] != "resolved":
        return _build_result(
            level_result["status"],
            reason=level_result["reason"],
            programme=programme,
            branch=branch,
            cycle=level_result["cycle"],
            academic_year=year_result["academic_year"],
            academic_year_name=year_result["academic_year_name"],
            warnings=level_result["warnings"],
        )

    class_queryset = AcademicClass.objects.filter(
        programme=programme,
        branch=branch,
        academic_year=year_result["academic_year"],
        level=level_result["resolved_level"],
        is_active=True,
    )
    match_count = class_queryset.count()

    if match_count == 0:
        return _build_result(
            "manual_required_missing_class",
            reason="academic_class_not_found",
            programme=programme,
            branch=branch,
            cycle=level_result["cycle"],
            academic_year=year_result["academic_year"],
            academic_year_name=year_result["academic_year_name"],
            resolved_level=level_result["resolved_level"],
            warnings=year_result["warnings"] + level_result["warnings"],
        )

    if match_count > 1:
        return _build_result(
            "manual_required_ambiguous_level",
            reason="multiple_academic_classes",
            programme=programme,
            branch=branch,
            cycle=level_result["cycle"],
            academic_year=year_result["academic_year"],
            academic_year_name=year_result["academic_year_name"],
            resolved_level=level_result["resolved_level"],
            warnings=year_result["warnings"] + level_result["warnings"],
        )

    academic_class = class_queryset.first()
    warnings = year_result["warnings"] + level_result["warnings"]
    if warnings:
        logger.info(
            "Academic context resolved with warnings candidature=%s warnings=%s",
            getattr(candidature, "pk", None),
            warnings,
        )

    return _build_result(
        "resolved",
        programme=programme,
        branch=branch,
        cycle=level_result["cycle"],
        academic_year=year_result["academic_year"],
        academic_year_name=year_result["academic_year_name"],
        resolved_level=level_result["resolved_level"],
        academic_class=academic_class,
        warnings=warnings,
    )
