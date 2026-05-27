from django.db.models import Count, Q, Sum
from django.utils import timezone

from branches.models import Branch
from formations.models import Cycle, Programme
from academics.models import AcademicClass

from marketing.models import Announcement, Campaign, DispatchLog, MarketingMedia, MarketingSettings, ProspectLead
from marketing.services.intelligence import build_marketing_guidance


def apply_marketing_filters(queryset, filters, *, branch_field="branches", formation_field="formations", cycle_field="cycles", class_field="classes"):
    branch = filters.get("branch")
    formation = filters.get("formation")
    cycle = filters.get("cycle")
    academic_class = filters.get("class")
    status = filters.get("status")
    q = filters.get("q")

    if branch:
        queryset = queryset.filter(Q(audience_scope="all") | Q(**{f"{branch_field}__id": branch})).distinct()
    if formation:
        queryset = queryset.filter(Q(audience_scope="all") | Q(**{f"{formation_field}__id": formation})).distinct()
    if cycle:
        queryset = queryset.filter(Q(audience_scope="all") | Q(**{f"{cycle_field}__id": cycle})).distinct()
    if academic_class:
        queryset = queryset.filter(Q(audience_scope="all") | Q(**{f"{class_field}__id": academic_class})).distinct()
    if status:
        queryset = queryset.filter(status=status)
    if q:
        if hasattr(queryset.model, "title"):
            queryset = queryset.filter(Q(title__icontains=q) | Q(content__icontains=q))
        elif hasattr(queryset.model, "name"):
            queryset = queryset.filter(Q(name__icontains=q) | Q(objective__icontains=q) | Q(content__icontains=q))
    return queryset


def get_filter_options():
    return {
        "branches": Branch.objects.filter(is_active=True).order_by("name"),
        "formations": Programme.objects.filter(is_active=True).select_related("cycle").order_by("title"),
        "cycles": Cycle.objects.filter(is_active=True).order_by("min_duration_years", "name"),
        "classes": AcademicClass.objects.filter(is_active=True, is_archived=False).select_related("branch", "programme").order_by("branch__name", "programme__title", "level")[:250],
    }


def build_marketing_dashboard_context(request):
    now = timezone.now()
    filters = {
        "branch": request.GET.get("branch") or "",
        "formation": request.GET.get("formation") or "",
        "cycle": request.GET.get("cycle") or "",
        "class": request.GET.get("class") or "",
        "status": request.GET.get("status") or "",
        "q": request.GET.get("q") or "",
    }

    announcements = apply_marketing_filters(
        Announcement.objects.prefetch_related("branches", "formations", "cycles", "classes").select_related("author"),
        filters,
    )
    campaigns = apply_marketing_filters(
        Campaign.objects.prefetch_related("branches", "formations", "cycles", "classes").select_related("created_by"),
        filters,
    )

    active_campaigns = campaigns.filter(status=Campaign.STATUS_ACTIVE)
    active_announcements = announcements.filter(status=Announcement.STATUS_ACTIVE)
    scheduled_campaigns = campaigns.filter(status=Campaign.STATUS_SCHEDULED)
    active_popups = announcements.filter(show_popup=True, status=Announcement.STATUS_ACTIVE).filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
    dispatches = DispatchLog.objects.all()
    sent_email_logs = dispatches.filter(channel__icontains="email", status=DispatchLog.STATUS_SENT)

    emails_sent = sent_email_logs.aggregate(total=Sum("recipients_count"))["total"] or 0
    opened = sent_email_logs.aggregate(total=Sum("opened_count"))["total"] or 0
    open_rate = round((opened / emails_sent) * 100, 1) if emails_sent else 0

    branch_activity = (
        Branch.objects.filter(is_active=True)
        .annotate(
            campaign_count=Count("campaign", distinct=True),
            announcement_count=Count("announcement", distinct=True),
        )
        .order_by("-campaign_count", "-announcement_count", "name")[:5]
    )

    upcoming_items = []
    for campaign in scheduled_campaigns.filter(starts_at__gte=now).order_by("starts_at")[:5]:
        upcoming_items.append({"kind": "Campagne", "title": campaign.name, "date": campaign.starts_at, "status": campaign.get_status_display()})
    for announcement in announcements.filter(starts_at__gte=now).order_by("starts_at")[:5]:
        upcoming_items.append({"kind": "Annonce", "title": announcement.title, "date": announcement.starts_at, "status": announcement.get_status_display()})
    upcoming_items = sorted(upcoming_items, key=lambda item: item["date"] or now)[:6]

    context = {
        "filters": filters,
        **get_filter_options(),
        "settings_obj": MarketingSettings.objects.first(),
        "kpis": {
            "active_campaigns": active_campaigns.count(),
            "active_announcements": active_announcements.count(),
            "emails_sent": emails_sent,
            "scheduled_campaigns": scheduled_campaigns.count(),
            "active_popups": active_popups.count(),
            "recent_prospects": ProspectLead.objects.filter(created_at__gte=now - timezone.timedelta(days=30)).count(),
            "open_rate": open_rate,
            "urgent_campaigns": campaigns.filter(status__in=[Campaign.STATUS_ACTIVE, Campaign.STATUS_SCHEDULED], ends_at__lte=now + timezone.timedelta(days=7)).count(),
        },
        "campaigns": campaigns.order_by("-created_at")[:8],
        "announcements": announcements.order_by("-created_at")[:8],
        "urgent_announcements": announcements.filter(priority__in=[Announcement.PRIORITY_HIGH, Announcement.PRIORITY_CRITICAL]).order_by("-created_at")[:6],
        "recent_activity": dispatches.select_related("announcement", "campaign", "created_by").order_by("-created_at")[:8],
        "media_items": MarketingMedia.objects.filter(is_archived=False).select_related("uploaded_by").prefetch_related("branches").order_by("-created_at")[:8],
        "prospects": ProspectLead.objects.select_related("interested_branch", "interested_programme").order_by("-created_at")[:8],
        "dispatch_logs": dispatches.select_related("announcement", "campaign", "created_by").order_by("-created_at")[:10],
        "branch_activity": branch_activity,
        "upcoming_items": upcoming_items,
        "guidance": build_marketing_guidance(filters=filters),
    }
    return context
