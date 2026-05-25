from academic_cycle.models import BranchAcademicCycle
from academic_cycle.services.readiness_service import generate_closure_report
from . import shared_task


@shared_task
def generate_branch_closure_report_task(branch_cycle_id):
    branch_cycle = BranchAcademicCycle.objects.get(pk=branch_cycle_id)
    return generate_closure_report(branch_cycle).pk
