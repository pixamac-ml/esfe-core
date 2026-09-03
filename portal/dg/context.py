"""Contexte institutionnel persistant du tableau de bord DG.

Le DG n'est pas limite a l'annexe de son profil : il peut passer d'une vue
consolidee a une annexe, tout en conservant l'annee academique choisie.
"""

from __future__ import annotations

from dataclasses import dataclass

from academics.models import AcademicYear

from .selectors import get_active_branches


SESSION_KEY = "dg_dashboard_context"
MODE_GLOBAL = "global"
MODE_BRANCH = "branch"


@dataclass(frozen=True)
class DgDashboardContext:
    academic_year: AcademicYear | None
    academic_years: list[AcademicYear]
    all_branches: list
    selected_branch: object | None
    mode: str

    @property
    def selected_branch_id(self) -> str:
        return str(self.selected_branch.id) if self.selected_branch else ""

    @property
    def scoped_branches(self) -> list:
        return [self.selected_branch] if self.selected_branch else self.all_branches

    @property
    def scoped_branch_ids(self) -> list[int]:
        return [branch.id for branch in self.scoped_branches]

    def contains_branch_id(self, branch_id) -> bool:
        try:
            return int(branch_id) in self.scoped_branch_ids
        except (TypeError, ValueError):
            return False

    @property
    def scope_label(self) -> str:
        if self.selected_branch:
            return f"Mode annexe - {self.selected_branch.name}"
        return "Mode global - Toutes les annexes"


def _resolve_academic_year(*, academic_years, raw_year_id, saved_context):
    requested_id = raw_year_id if raw_year_id is not None else saved_context.get("academic_year_id")
    if str(requested_id or "").isdigit():
        selected = next((year for year in academic_years if year.id == int(requested_id)), None)
        if selected:
            return selected
    return next((year for year in academic_years if year.is_active), None) or (academic_years[0] if academic_years else None)


def _resolve_branch(*, branches, raw_branch_id, saved_context):
    requested_id = raw_branch_id if raw_branch_id is not None else saved_context.get("branch_id")
    if str(requested_id or "").isdigit():
        return next((branch for branch in branches if branch.id == int(requested_id)), None)
    return None


def resolve_dg_context(request, *, accept_legacy_branch_param=True) -> DgDashboardContext:
    """Validate then persist the DG's academic year and global/branch scope.

    Query parameters take precedence over the saved context.  IDs are accepted
    only when they resolve to an existing academic year or active branch;
    arbitrary client values therefore cannot widen or corrupt the scope.
    """

    academic_years = list(AcademicYear.objects.order_by("-start_date", "-id"))
    all_branches = list(get_active_branches())
    saved_context = request.session.get(SESSION_KEY, {})

    raw_year_id = (
        request.GET.get("academic_year_id")
        if "academic_year_id" in request.GET
        else request.POST.get("academic_year_id") if "academic_year_id" in request.POST else None
    )
    if "scope_branch_id" in request.GET or "scope_branch_id" in request.POST:
        raw_branch_id = request.GET.get("scope_branch_id") if "scope_branch_id" in request.GET else request.POST.get("scope_branch_id")
    elif accept_legacy_branch_param and "branch_id" in request.GET:
        # Kept for bookmarked dashboard URLs. Drawers use ``branch_id`` for
        # their target object and deliberately disable this legacy behaviour.
        raw_branch_id = request.GET.get("branch_id")
    else:
        raw_branch_id = None
    academic_year = _resolve_academic_year(
        academic_years=academic_years,
        raw_year_id=raw_year_id,
        saved_context=saved_context,
    )
    selected_branch = _resolve_branch(
        branches=all_branches,
        raw_branch_id=raw_branch_id,
        saved_context=saved_context,
    )
    mode = MODE_BRANCH if selected_branch else MODE_GLOBAL

    persisted = {
        "academic_year_id": academic_year.id if academic_year else None,
        "branch_id": selected_branch.id if selected_branch else None,
        "mode": mode,
    }
    if saved_context != persisted:
        request.session[SESSION_KEY] = persisted

    return DgDashboardContext(
        academic_year=academic_year,
        academic_years=academic_years,
        all_branches=all_branches,
        selected_branch=selected_branch,
        mode=mode,
    )
