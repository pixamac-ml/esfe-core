from django.urls import path
from .views import *
from django.contrib.auth import views as auth_views
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