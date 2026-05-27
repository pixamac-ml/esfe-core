from django import forms

from .models import Announcement, Campaign, MarketingMedia, MarketingSettings, ProspectLead


class MarketingFormMixin:
    datetime_fields = {"starts_at", "ends_at", "scheduled_at"}
    placeholders = {
        "title": "Ex: Journee culturelle Jiribougou",
        "name": "Ex: Campagne inscriptions 2026",
        "objective": "Ex: Relancer les prospects qualifies avant vendredi",
        "content": "Redige le message principal, les liens et les consignes de diffusion.",
        "full_name": "Nom complet du prospect",
        "email": "adresse@email.com",
        "phone": "+223 ...",
        "city": "Ville",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "mk-checkbox")
            elif isinstance(field.widget, forms.SelectMultiple):
                field.widget.attrs.setdefault("class", "mk-select")
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs.setdefault("class", "mk-textarea")
            else:
                field.widget.attrs.setdefault("class", "mk-input")
            if name in self.placeholders:
                field.widget.attrs.setdefault("placeholder", self.placeholders[name])
            if name in self.datetime_fields:
                field.widget.input_type = "datetime-local"


class AnnouncementForm(MarketingFormMixin, forms.ModelForm):
    class Meta:
        model = Announcement
        fields = [
            "title",
            "announcement_type",
            "priority",
            "status",
            "content",
            "audience_scope",
            "branches",
            "formations",
            "cycles",
            "classes",
            "show_popup",
            "is_blocking_popup",
            "starts_at",
            "ends_at",
            "scheduled_at",
        ]
        widgets = {"content": forms.Textarea(attrs={"rows": 6})}


class CampaignForm(MarketingFormMixin, forms.ModelForm):
    class Meta:
        model = Campaign
        fields = [
            "name",
            "objective",
            "status",
            "channel",
            "audience_scope",
            "branches",
            "formations",
            "cycles",
            "classes",
            "starts_at",
            "ends_at",
            "budget_estimate",
            "content",
            "progress",
        ]
        widgets = {"content": forms.Textarea(attrs={"rows": 6})}


class ProspectLeadForm(MarketingFormMixin, forms.ModelForm):
    class Meta:
        model = ProspectLead
        fields = [
            "full_name",
            "email",
            "phone",
            "city",
            "interested_branch",
            "interested_programme",
            "source",
            "consent_email",
        ]


class MarketingMediaForm(MarketingFormMixin, forms.ModelForm):
    class Meta:
        model = MarketingMedia
        fields = ["title", "media_type", "file", "branches", "is_archived"]


class MarketingSettingsForm(MarketingFormMixin, forms.ModelForm):
    class Meta:
        model = MarketingSettings
        fields = [
            "sender_email",
            "sender_name",
            "brevo_api_key_label",
            "popup_primary_color",
            "popup_duration_seconds",
            "notification_behaviour",
        ]
