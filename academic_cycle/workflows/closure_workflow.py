from academic_cycle.services.closure_service import close_branch_cycle, start_deliberation
from academic_cycle.services.readiness_service import generate_closure_report


def run_branch_closure_workflow(branch_cycle, actor):
    report = generate_closure_report(branch_cycle, actor=actor)
    if report.status == "valid":
        start_deliberation(branch_cycle, actor)
        close_branch_cycle(branch_cycle, actor)
    return report
