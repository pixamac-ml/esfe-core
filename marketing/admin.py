from django.contrib import admin

from .models import (
    Announcement,
    Campaign,
    CampaignAudience,
    DispatchLog,
    MarketingMedia,
    MarketingSettings,
    ProspectLead,
    ScheduledCampaign,
)


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "announcement_type", "priority", "status", "audience_scope", "starts_at", "ends_at")
    list_filter = ("announcement_type", "priority", "status", "audience_scope", "show_popup")
    search_fields = ("title", "content")
    filter_horizontal = ("branches", "formations", "cycles", "classes")
    date_hierarchy = "created_at"


class CampaignAudienceInline(admin.TabularInline):
    model = CampaignAudience
    extra = 0


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "channel", "audience_scope", "starts_at", "ends_at", "progress")
    list_filter = ("status", "channel", "audience_scope")
    search_fields = ("name", "objective", "content")
    filter_horizontal = ("branches", "formations", "cycles", "classes")
    inlines = [CampaignAudienceInline]
    date_hierarchy = "created_at"


@admin.register(MarketingMedia)
class MarketingMediaAdmin(admin.ModelAdmin):
    list_display = ("title", "media_type", "is_archived", "uploaded_by", "created_at")
    list_filter = ("media_type", "is_archived")
    search_fields = ("title",)
    filter_horizontal = ("branches",)


@admin.register(ProspectLead)
class ProspectLeadAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "phone", "city", "interested_branch", "source", "created_at")
    list_filter = ("source", "interested_branch", "consent_email")
    search_fields = ("full_name", "email", "phone", "city")


@admin.register(DispatchLog)
class DispatchLogAdmin(admin.ModelAdmin):
    list_display = ("channel", "provider", "status", "recipients_count", "opened_count", "created_at")
    list_filter = ("channel", "provider", "status")
    search_fields = ("error_message",)
    readonly_fields = ("created_at",)


@admin.register(ScheduledCampaign)
class ScheduledCampaignAdmin(admin.ModelAdmin):
    list_display = ("campaign", "scheduled_for", "recurrence", "expires_at", "is_processed")
    list_filter = ("is_processed", "recurrence")
    search_fields = ("campaign__name",)


@admin.register(MarketingSettings)
class MarketingSettingsAdmin(admin.ModelAdmin):
    list_display = ("sender_email", "sender_name", "popup_primary_color", "popup_duration_seconds", "updated_at")
