from django.db import transaction

from marketing.models import Campaign, DispatchLog, ProspectLead, ScheduledCampaign


def estimate_campaign_audience(campaign):
    leads = ProspectLead.objects.filter(consent_email=True)
    if campaign.audience_scope != Campaign.SCOPE_ALL:
        branch_ids = campaign.branches.values_list("id", flat=True)
        programme_ids = campaign.formations.values_list("id", flat=True)
        if branch_ids:
            leads = leads.filter(interested_branch_id__in=branch_ids)
        if programme_ids:
            leads = leads.filter(interested_programme_id__in=programme_ids)
    return leads.count()


@transaction.atomic
def prepare_campaign(campaign, *, actor=None):
    estimated_size = estimate_campaign_audience(campaign)
    campaign.audience_segments.get_or_create(
        name="Audience principale",
        defaults={
            "source": "prospects",
            "filters": {
                "audience_scope": campaign.audience_scope,
                "branches": list(campaign.branches.values_list("id", flat=True)),
                "formations": list(campaign.formations.values_list("id", flat=True)),
            },
            "estimated_size": estimated_size,
        },
    )
    if campaign.status == Campaign.STATUS_DRAFT and campaign.starts_at:
        campaign.status = Campaign.STATUS_SCHEDULED
        campaign.save(update_fields=["status", "updated_at"])
        ScheduledCampaign.objects.get_or_create(campaign=campaign, scheduled_for=campaign.starts_at)
    return campaign


def create_dispatch_log(*, campaign=None, announcement=None, channel, actor=None, status=DispatchLog.STATUS_PENDING, recipients_count=0, opened_count=0, provider=""):
    audience_source = campaign or announcement
    snapshot = {}
    if audience_source:
        snapshot = {
            "scope": audience_source.audience_scope,
            "branches": list(audience_source.branches.values_list("id", flat=True)),
            "formations": list(audience_source.formations.values_list("id", flat=True)),
            "cycles": list(audience_source.cycles.values_list("id", flat=True)),
            "classes": list(audience_source.classes.values_list("id", flat=True)),
        }
    return DispatchLog.objects.create(
        campaign=campaign,
        announcement=announcement,
        channel=channel,
        provider=provider,
        status=status,
        audience_snapshot=snapshot,
        recipients_count=recipients_count,
        opened_count=opened_count,
        created_by=actor,
    )

