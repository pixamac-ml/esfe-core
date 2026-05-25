from academic_cycle.services.activation_service import activate_academic_year_for_branch, migrate_branch_dashboards


def run_branch_activation_workflow(source_branch_cycle, target_year, actor):
    target_cycle = activate_academic_year_for_branch(source_branch_cycle.branch, target_year, actor)
    migration = migrate_branch_dashboards(source_branch_cycle, target_year, actor)
    return {"target_cycle": target_cycle, "migration": migration}
