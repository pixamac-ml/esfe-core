from academics.models import AcademicYear
from academic_cycle.models import BranchAcademicCycle
from academic_cycle.services.reenrollment_service import prepare_reenrollments_for_branch
from . import shared_task


@shared_task
def prepare_reenrollments_for_branch_task(branch_cycle_id, target_year_id):
    branch_cycle = BranchAcademicCycle.objects.get(pk=branch_cycle_id)
    target_year = AcademicYear.objects.get(pk=target_year_id)
    return len(prepare_reenrollments_for_branch(branch_cycle, target_year))
