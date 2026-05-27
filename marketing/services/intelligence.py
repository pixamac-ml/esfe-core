from django.db.models import Count, Q, Sum
from django.utils import timezone

from branches.models import Branch
from marketing.models import Announcement, Campaign, DispatchLog, MarketingMedia, ProspectLead


def _score_health(value, warning_at, danger_at):
    if value >= danger_at:
        return "danger"
    if value >= warning_at:
        return "warning"
    return "good"


def build_marketing_guidance(*, filters=None):
    filters = filters or {}
    now = timezone.now()
    last_30_days = now - timezone.timedelta(days=30)

    active_campaigns = Campaign.objects.filter(status=Campaign.STATUS_ACTIVE)
    scheduled_without_dates = Campaign.objects.filter(status=Campaign.STATUS_SCHEDULED, starts_at__isnull=True).count()
    urgent_announcements = Announcement.objects.filter(
        priority__in=[Announcement.PRIORITY_HIGH, Announcement.PRIORITY_CRITICAL],
        status__in=[Announcement.STATUS_ACTIVE, Announcement.STATUS_SCHEDULED],
    )
    email_logs = DispatchLog.objects.filter(channel__icontains="email", created_at__gte=last_30_days)
    sent = email_logs.filter(status=DispatchLog.STATUS_SENT).aggregate(total=Sum("recipients_count"))["total"] or 0
    opened = email_logs.filter(status=DispatchLog.STATUS_SENT).aggregate(total=Sum("opened_count"))["total"] or 0
    open_rate = round((opened / sent) * 100, 1) if sent else 0
    prospects_without_consent = ProspectLead.objects.filter(consent_email=False).count()
    media_without_branch = MarketingMedia.objects.filter(is_archived=False, branches__isnull=True).distinct().count()

    recommendations = []
    if scheduled_without_dates:
        recommendations.append({
            "level": "danger",
            "title": "Campagnes planifiees sans date",
            "body": "Ajoute une date de debut pour que Celery puisse les traiter proprement.",
            "metric": scheduled_without_dates,
        })
    if urgent_announcements.count():
        recommendations.append({
            "level": "warning",
            "title": "Communications prioritaires",
            "body": "Controle l'expiration et le ciblage avant toute rediffusion.",
            "metric": urgent_announcements.count(),
        })
    if sent and open_rate < 18:
        recommendations.append({
            "level": "warning",
            "title": "Ouverture email faible",
            "body": "Teste un objet plus direct et segmente par annexe ou formation.",
            "metric": f"{open_rate}%",
        })
    if prospects_without_consent:
        recommendations.append({
            "level": "warning",
            "title": "Prospects non contactables",
            "body": "Separe-les des audiences email Brevo pour eviter une diffusion inutile.",
            "metric": prospects_without_consent,
        })
    if media_without_branch:
        recommendations.append({
            "level": "info",
            "title": "Medias sans annexe",
            "body": "Associe les affiches aux annexes pour faciliter la reutilisation locale.",
            "metric": media_without_branch,
        })
    if not recommendations:
        recommendations.append({
            "level": "good",
            "title": "Pilotage stable",
            "body": "Les campagnes, audiences et medias n'ont pas d'anomalie immediate.",
            "metric": "OK",
        })

    branch_pressure = (
        Branch.objects.filter(is_active=True)
        .annotate(
            active_campaigns=Count("campaign", filter=Q(campaign__status=Campaign.STATUS_ACTIVE), distinct=True),
            active_announcements=Count("announcement", filter=Q(announcement__status=Announcement.STATUS_ACTIVE), distinct=True),
            recent_prospects=Count("marketing_prospects", filter=Q(marketing_prospects__created_at__gte=last_30_days), distinct=True),
        )
        .order_by("-active_campaigns", "-active_announcements", "-recent_prospects", "name")[:8]
    )

    workload = active_campaigns.count() + urgent_announcements.count()
    return {
        "recommendations": recommendations[:5],
        "workload": {
            "value": workload,
            "health": _score_health(workload, 6, 10),
            "label": "Charge diffusion",
        },
        "open_rate": {
            "value": open_rate,
            "health": "good" if open_rate >= 25 or not sent else "warning",
            "label": "Ouverture 30 jours",
        },
        "branch_pressure": branch_pressure,
    }


def build_audience_estimate(*, audience_scope="all", branch_ids=None, programme_ids=None):
    leads = ProspectLead.objects.filter(consent_email=True)
    if audience_scope != "all":
        if branch_ids:
            leads = leads.filter(interested_branch_id__in=branch_ids)
        if programme_ids:
            leads = leads.filter(interested_programme_id__in=programme_ids)
    total = leads.count()
    email_ready = leads.exclude(email="").count()
    phone_ready = leads.exclude(phone="").count()
    return {
        "total": total,
        "email_ready": email_ready,
        "phone_ready": phone_ready,
        "quality": "forte" if total and email_ready / max(total, 1) >= 0.75 else "a verifier",
    }


def get_object_guidance(obj):
    checks = []
    if isinstance(obj, Campaign):
        estimate = build_audience_estimate(
            audience_scope=obj.audience_scope,
            branch_ids=list(obj.branches.values_list("id", flat=True)),
            programme_ids=list(obj.formations.values_list("id", flat=True)),
        )
        checks.append(("Audience email", f"{estimate['email_ready']} contact(s) email pret(s)", estimate["quality"]))
        if obj.status == Campaign.STATUS_DRAFT:
            checks.append(("Action conseillee", "Finaliser le ciblage puis preparer Brevo", "a faire"))
        if obj.starts_at is None:
            checks.append(("Planification", "Date de debut non definie", "a faire"))
    elif isinstance(obj, Announcement):
        if obj.show_popup and obj.ends_at is None:
            checks.append(("Expiration popup", "Ajouter une date de fin pour eviter un popup permanent", "a faire"))
        checks.append(("Ciblage", obj.audience_label, "pret"))
        checks.append(("Canaux", ", ".join(obj.channels or ["notification"]), "pret"))
    return checks
