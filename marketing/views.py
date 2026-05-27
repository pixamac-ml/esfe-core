from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.forms import ProfileForm, UserPreferenceForm
from accounts.models import PayrollEntry, Profile, UserPreference
from communication.models import CommunicationNotification
from communication.selectors import get_user_notifications, get_user_unread_count
from communication.services import NotificationService
from .forms import AnnouncementForm, CampaignForm, MarketingMediaForm, MarketingSettingsForm, ProspectLeadForm
from .models import Announcement, Campaign, MarketingMedia, MarketingSettings, ProspectLead
from .permissions import marketing_required
from .selectors import build_marketing_dashboard_context
from .services.brevo_service import prepare_brevo_campaign
from .services.campaign_service import prepare_campaign
from .services.notification_service import publish_announcement
from .services.intelligence import build_audience_estimate, get_object_guidance


def _paginate(request, queryset, per_page=10, page_param="page"):
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(request.GET.get(page_param))


def _style_profile_form(form):
    for field_name, field in form.fields.items():
        if field_name == "avatar":
            field.widget.attrs.update({
                "class": "sg-form-input",
                "accept": "image/jpeg,image/png,image/webp",
            })
        elif field.widget.__class__.__name__ == "Textarea":
            field.widget.attrs.update({"class": "sg-form-input", "rows": 3})
        else:
            field.widget.attrs.update({"class": "sg-form-input"})
    return form


def _marketing_profile_form(instance):
    return _style_profile_form(ProfileForm(instance=instance))


def _style_preference_form(form):
    for field in form.fields.values():
        field.widget.attrs.update({"style": "width:18px;height:18px;flex-shrink:0;"})
    return form


def _marketing_preference_form(instance):
    return _style_preference_form(UserPreferenceForm(instance=instance))


def _build_account_context(request, *, selected_notification=None, profile_form=None, preference_form=None):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    preference, _ = UserPreference.objects.get_or_create(user=request.user)

    payroll_queryset = (
        PayrollEntry.objects
        .filter(employee=request.user)
        .select_related("branch", "created_by", "updated_by")
    )
    salary_entries_page = _paginate(request, payroll_queryset, per_page=8, page_param="salary_page")

    notifications_queryset = get_user_notifications(
        request.user,
        channel=CommunicationNotification.CHANNEL_IN_APP,
    )
    notifications_page = _paginate(request, notifications_queryset, per_page=10, page_param="notifications_page")

    return {
        "marketing_profile": profile,
        "marketing_preference": preference,
        "profile_form": profile_form or _marketing_profile_form(profile),
        "preference_form": preference_form or _marketing_preference_form(preference),
        "salary_entries_page": salary_entries_page,
        "salary_entries": salary_entries_page.object_list,
        "latest_salary_entry": payroll_queryset.first(),
        "notifications_page": notifications_page,
        "notifications_rows": notifications_page.object_list,
        "selected_notification": selected_notification,
        "messages_count": get_user_unread_count(request.user),
    }


@login_required
@marketing_required
def dashboard(request):
    context = build_marketing_dashboard_context(request)
    context.update(_build_account_context(request))
    return render(request, "marketing/dashboard.html", context)


@login_required
@marketing_required
def htmx_workspace(request):
    context = build_marketing_dashboard_context(request)
    context.update(_build_account_context(request))
    return render(request, "marketing/partials/workspace.html", context)


@login_required
@marketing_required
def account_salary_panel(request):
    context = _build_account_context(request)
    return render(request, "marketing/partials/account_salary.html", context)


@login_required
@marketing_required
def account_notifications_panel(request):
    selected_notification = None
    notification_id = request.GET.get("notification_id")
    if notification_id:
        selected_notification = get_object_or_404(
            CommunicationNotification.objects.select_related("actor", "event"),
            pk=notification_id,
            recipient=request.user,
            channel=CommunicationNotification.CHANNEL_IN_APP,
        )
        NotificationService.mark_as_read(selected_notification)
    context = _build_account_context(request, selected_notification=selected_notification)
    return render(request, "marketing/partials/account_notifications.html", context)


@login_required
@marketing_required
def account_settings_panel(request):
    context = _build_account_context(request)
    return render(request, "marketing/partials/account_settings.html", context)


@login_required
@marketing_required
@require_POST
def profile_update(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    form = ProfileForm(request.POST, request.FILES, instance=profile)
    if form.is_valid():
        form.save()
        messages.success(request, "Profil mis a jour.")
        form = None
    else:
        messages.error(request, "Le profil contient des informations a corriger.")
        form = _style_profile_form(form)
    context = _build_account_context(request, profile_form=form)
    if request.headers.get("HX-Request") == "true":
        return render(request, "marketing/partials/account_settings.html", context)
    return redirect("marketing:dashboard")


@login_required
@marketing_required
@require_POST
def preferences_update(request):
    preference, _ = UserPreference.objects.get_or_create(user=request.user)
    form = UserPreferenceForm(request.POST, instance=preference)
    if form.is_valid():
        form.save()
        messages.success(request, "Preferences mises a jour.")
        form = None
    else:
        messages.error(request, "Les preferences contiennent des informations a corriger.")
        form = _style_preference_form(form)
    context = _build_account_context(request, preference_form=form)
    if request.headers.get("HX-Request") == "true":
        return render(request, "marketing/partials/account_settings.html", context)
    return redirect("marketing:dashboard")


@login_required
@marketing_required
def htmx_audience_estimate(request):
    estimate = build_audience_estimate(
        audience_scope=request.GET.get("audience_scope") or "all",
        branch_ids=request.GET.getlist("branches"),
        programme_ids=request.GET.getlist("formations"),
    )
    return render(request, "marketing/partials/audience_estimate.html", {"estimate": estimate})


@login_required
@marketing_required
def campaign_drawer(request, pk):
    campaign = get_object_or_404(
        Campaign.objects.prefetch_related("branches", "formations", "cycles", "classes"),
        pk=pk,
    )
    return render(
        request,
        "marketing/partials/object_drawer.html",
        {
            "object": campaign,
            "object_type": "campaign",
            "checks": get_object_guidance(campaign),
            "logs": campaign.dispatch_logs.select_related("created_by").order_by("-created_at")[:10],
        },
    )


@login_required
@marketing_required
def announcement_drawer(request, pk):
    announcement = get_object_or_404(
        Announcement.objects.prefetch_related("branches", "formations", "cycles", "classes"),
        pk=pk,
    )
    return render(
        request,
        "marketing/partials/object_drawer.html",
        {
            "object": announcement,
            "object_type": "announcement",
            "checks": get_object_guidance(announcement),
            "logs": announcement.dispatch_logs.select_related("created_by").order_by("-created_at")[:10],
        },
    )


@login_required
@marketing_required
def announcement_create(request):
    form = AnnouncementForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        announcement = form.save(commit=False)
        announcement.author = request.user
        announcement.channels = request.POST.getlist("channels") or ["popup", "notification"]
        announcement.save()
        form.save_m2m()
        if "publish_now" in request.POST:
            announcement.status = Announcement.STATUS_ACTIVE
            announcement.save(update_fields=["status", "updated_at"])
            publish_announcement(announcement, actor=request.user)
            messages.success(request, "Annonce publiee et diffusee.")
        else:
            messages.success(request, "Annonce enregistree.")
        return redirect("marketing:dashboard")
    return render(
        request,
        "marketing/form.html",
        {
            "form": form,
            "form_kind": "announcement",
            "title": "Nouvelle annonce",
            "submit_label": "Enregistrer",
        },
    )


@login_required
@marketing_required
def announcement_publish(request, pk):
    announcement = get_object_or_404(Announcement, pk=pk)
    announcement.status = Announcement.STATUS_ACTIVE
    announcement.save(update_fields=["status", "updated_at"])
    count = publish_announcement(announcement, actor=request.user)
    messages.success(request, f"Annonce diffusee a {count} destinataire(s).")
    return redirect("marketing:dashboard")


@login_required
@marketing_required
def campaign_create(request):
    form = CampaignForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        campaign = form.save(commit=False)
        campaign.created_by = request.user
        campaign.save()
        form.save_m2m()
        prepare_campaign(campaign, actor=request.user)
        if "prepare_brevo" in request.POST:
            prepare_brevo_campaign(campaign, actor=request.user)
            messages.success(request, "Campagne preparee pour Brevo.")
        else:
            messages.success(request, "Campagne enregistree.")
        return redirect("marketing:dashboard")
    return render(
        request,
        "marketing/form.html",
        {
            "form": form,
            "form_kind": "campaign",
            "title": "Nouvelle campagne",
            "submit_label": "Enregistrer",
        },
    )


@login_required
@marketing_required
def campaign_prepare_brevo(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    prepare_campaign(campaign, actor=request.user)
    prepare_brevo_campaign(campaign, actor=request.user)
    messages.success(request, "Diffusion email Brevo preparee.")
    return redirect("marketing:dashboard")


@login_required
@marketing_required
def prospect_create(request):
    form = ProspectLeadForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Prospect ajoute.")
        return redirect("marketing:dashboard")
    return render(request, "marketing/form.html", {"form": form, "form_kind": "generic", "title": "Nouveau prospect", "submit_label": "Ajouter"})


@login_required
@marketing_required
def media_create(request):
    form = MarketingMediaForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        media = form.save(commit=False)
        media.uploaded_by = request.user
        media.save()
        form.save_m2m()
        messages.success(request, "Media ajoute a la bibliotheque.")
        return redirect("marketing:dashboard")
    return render(request, "marketing/form.html", {"form": form, "form_kind": "generic", "title": "Nouveau media", "submit_label": "Importer"})


@login_required
@marketing_required
def media_archive(request, pk):
    media = get_object_or_404(MarketingMedia, pk=pk)
    media.is_archived = True
    media.save(update_fields=["is_archived"])
    messages.success(request, "Media archive.")
    return redirect("marketing:dashboard")


@login_required
@marketing_required
def settings_view(request):
    settings_obj, _ = MarketingSettings.objects.get_or_create(pk=1)
    form = MarketingSettingsForm(request.POST or None, instance=settings_obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Parametres marketing mis a jour.")
        return redirect("marketing:dashboard")
    return render(request, "marketing/form.html", {"form": form, "form_kind": "generic", "title": "Parametres marketing", "submit_label": "Enregistrer"})
