from academic_cycle.services.correction_service import assign_correction_request, resolve_correction_request


def run_correction_resolution(correction, assignee, actor, note):
    assign_correction_request(correction, assignee, actor)
    return resolve_correction_request(correction, actor, note)
