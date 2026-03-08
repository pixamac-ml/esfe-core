from django.urls import path
from .views import *
from django.contrib.auth import views as auth_views
from .dashboard_views import *
app_name = "accounts"

urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="accounts/registration/login.html"
        ),
        name="login",
    ),

    path(
        "logout/",
        auth_views.LogoutView.as_view(
            template_name="registration/logged_out.html"
        ),
        name="logout",
    ),

    path("dashboard/", dashboard_redirect, name="dashboard_redirect"),
    path("dashboard/admissions/", admissions_dashboard, name="admissions_dashboard"),
    path("dashboard/finance/", finance_dashboard, name="finance_dashboard"),
    path("dashboard/executive/", executive_dashboard, name="executive_dashboard"),

    # ========================
    # AUTH PERSONNALISÉ
    # ========================
    path("register/", register, name="register"),

    # ========================
    # PROFIL UTILISATEUR
    # ========================
    path("profile/", profile_detail, name="profile"),
    path("profile/edit/", edit_profile, name="edit_profile"),
    path("profile/email/", update_email, name="update_email"),

    # ======================================================
    # PROFIL - ONGLETS HTMX
    # ======================================================
    path(
        "profile/activity/",
        profile_activity,
        name="profile_activity"
    ),

    path(
        "profile/topics/",
        profile_topics,
        name="profile_topics"
    ),

    path(
        "profile/answers/",
        profile_answers,
        name="profile_answers"
    ),

    path(
        "profile/badges/",
        profile_badges,
        name="profile_badges"
    ),

    path(
        "profile/settings/",
        profile_settings,
        name="profile_settings"
    ),
]
