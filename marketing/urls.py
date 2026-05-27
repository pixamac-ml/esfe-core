from django.urls import path

from . import views

app_name = "marketing"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("htmx/workspace/", views.htmx_workspace, name="htmx_workspace"),
    path("htmx/audience-estimate/", views.htmx_audience_estimate, name="htmx_audience_estimate"),
    path("account/salary/", views.account_salary_panel, name="account_salary"),
    path("account/notifications/", views.account_notifications_panel, name="account_notifications"),
    path("account/settings/", views.account_settings_panel, name="account_settings"),
    path("account/profile/update/", views.profile_update, name="profile_update"),
    path("account/preferences/update/", views.preferences_update, name="preferences_update"),
    path("campaigns/<int:pk>/drawer/", views.campaign_drawer, name="campaign_drawer"),
    path("announcements/<int:pk>/drawer/", views.announcement_drawer, name="announcement_drawer"),
    path("announcements/create/", views.announcement_create, name="announcement_create"),
    path("announcements/<int:pk>/publish/", views.announcement_publish, name="announcement_publish"),
    path("campaigns/create/", views.campaign_create, name="campaign_create"),
    path("campaigns/<int:pk>/prepare-brevo/", views.campaign_prepare_brevo, name="campaign_prepare_brevo"),
    path("prospects/create/", views.prospect_create, name="prospect_create"),
    path("media/create/", views.media_create, name="media_create"),
    path("media/<int:pk>/archive/", views.media_archive, name="media_archive"),
    path("settings/", views.settings_view, name="settings"),
]
