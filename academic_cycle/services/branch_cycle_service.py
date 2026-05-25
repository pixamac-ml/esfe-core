from academic_cycle.models import BranchAcademicCycle


def get_or_create_branch_cycle(branch, academic_year, defaults=None):
    return BranchAcademicCycle.objects.get_or_create(branch=branch, academic_year=academic_year, defaults=defaults or {})
