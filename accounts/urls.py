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

    # ========================
    # HTMX ENDPOINTS - FINANCE
    # ========================
    path(
        "dashboard/finance/payment/<int:payment_id>/validate/",
        validate_payment_htmx,
        name="validate_payment_htmx"
    ),
    path(
        "dashboard/finance/payment/<int:payment_id>/reject/",
        reject_payment_htmx,
        name="reject_payment_htmx"
    ),

    # ========================
    # HTMX ENDPOINTS - CASH PAYMENT SESSIONS
    # ========================
    path(
        "dashboard/finance/cash-session/create/",
        create_cash_session_htmx,
        name="create_cash_session_htmx"
    ),
    path(
        "dashboard/finance/cash-session/<int:session_id>/regenerate-code/",
        regenerate_code_htmx,
        name="regenerate_code_htmx"
    ),
    path(
        "dashboard/finance/cash-session/<int:session_id>/mark-used/",
        mark_session_used_htmx,
        name="mark_session_used_htmx"
    ),

    # ========================
    # HTMX ENDPOINTS - ADMISSIONS
    # ========================
    path(
        "dashboard/admissions/candidature/<int:candidature_id>/approve/",
        approve_candidature_htmx,
        name="approve_candidature_htmx"
    ),
    path(
        "dashboard/admissions/candidature/<int:candidature_id>/reject/",
        reject_candidature_htmx,
        name="reject_candidature_htmx"
    ),
    path(
        "dashboard/admissions/document/<int:document_id>/validate/",
        validate_document_htmx,
        name="validate_document_htmx"
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


    # Dans accounts/urls.py, ajouter :

    # Détails
    path('htmx/candidature/<int:candidature_id>/detail/', get_candidature_detail_htmx, name='candidature_detail_htmx'),
    path('htmx/inscription/<int:inscription_id>/detail/', get_inscription_detail_htmx, name='inscription_detail_htmx'),

    # Suppression
    path('htmx/candidature/<int:candidature_id>/delete/', delete_candidature_htmx, name='delete_candidature_htmx'),

    # Exports
    path('export/candidatures/', export_candidatures_csv, name='export_candidatures_csv'),
    path('export/payments/', export_payments_csv, name='export_payments_csv'),
    path('dashboard/executive/export/', export_executive_csv, name='export_executive_csv'),


    # ========================
    # HTMX ENDPOINTS - ADMISSIONS
    # ========================
    path(
        "dashboard/admissions/candidature/<int:candidature_id>/approve/",
        approve_candidature_htmx,
        name="approve_candidature_htmx"
    ),
    path(
        "dashboard/admissions/candidature/<int:candidature_id>/under-review/",
        set_candidature_under_review_htmx,
        name="set_candidature_under_review_htmx"
    ),
    path(
        "dashboard/admissions/candidature/<int:candidature_id>/to-complete/",
        set_candidature_to_complete_htmx,
        name="set_candidature_to_complete_htmx"
    ),
    path(
        "dashboard/admissions/candidature/<int:candidature_id>/reject/",
        reject_candidature_htmx,
        name="reject_candidature_htmx"
    ),
    path(
        "dashboard/admissions/candidature/<int:candidature_id>/create-inscription/",
        create_inscription_htmx,
        name="create_inscription_htmx"
    ),
    path(
        "dashboard/admissions/document/<int:document_id>/validate/",
        validate_document_htmx,
        name="validate_document_htmx"
    ),



]