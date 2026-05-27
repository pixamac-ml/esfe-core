from marketing.models import DispatchLog
from .campaign_service import create_dispatch_log, estimate_campaign_audience


def prepare_brevo_campaign(campaign, *, actor=None):
    recipients_count = estimate_campaign_audience(campaign)
    return create_dispatch_log(
        campaign=campaign,
        channel="email",
        provider="brevo",
        actor=actor,
        status=DispatchLog.STATUS_PENDING,
        recipients_count=recipients_count,
    )


def sync_prospect_to_brevo(prospect):
    # V1 keeps the Brevo boundary explicit. Real API calls remain in communication providers.
    prospect.tags = list({*(prospect.tags or []), "brevo-ready"})
    prospect.save(update_fields=["tags", "updated_at"])
    return prospect

