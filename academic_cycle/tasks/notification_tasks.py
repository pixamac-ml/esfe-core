from academic_cycle.services.notification_service import emit_cycle_event
from . import shared_task


@shared_task
def emit_cycle_event_task(event_name, payload):
    return emit_cycle_event(event_name, payload)
