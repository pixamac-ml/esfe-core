from django.urls import path
from .views import (
    register,
    edit_profile,
    update_email,
    profile_detail,
)
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

]