"""
Celery-ready task entrypoints for marketing scheduling.

The project can wire these functions to Celery later without moving business
logic out of the services.
"""

from django.utils import timezone

from marketing.models import ScheduledCampaign
from marketing.services.brevo_service import prepare_brevo_campaign


def process_due_scheduled_campaigns():
    due_schedules = ScheduledCampaign.objects.select_related("campaign").filter(
        is_processed=False,
        scheduled_for__lte=timezone.now(),
    )
    processed = 0
    for schedule in due_schedules:
        prepare_brevo_campaign(schedule.campaign)
        schedule.is_processed = True
        schedule.save(update_fields=["is_processed"])
        processed += 1
    return processed
