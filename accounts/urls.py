# accounts/urls.py

from django.urls import path
from django.contrib.auth import views as auth_views

from .auth_views import PortalLoginView

# Import des vues principales
from .views import (
    register,
    edit_profile,
    update_email,
    profile_detail,
    profile_activity,
    profile_topics,
    profile_answers,
    profile_badges,
    profile_settings,
    dashboard_redirect,
)

# Import des dashboards
from .dashboards.admissions_dashboard import admissions_dashboard
from .dashboards.finance_dashboard import finance_dashboard
from .dashboards.executive_dashboard import executive_dashboard

# Import des vues HTMX Admissions
from .dashboards.htmx_admissions import (
    approve_candidature_htmx,
    reject_candidature_htmx,
    validate_document_htmx,
    set_candidature_under_review_htmx,
    set_candidature_to_complete_htmx,
    create_inscription_htmx,
    get_candidature_detail_htmx,
    get_inscription_detail_htmx,
    delete_candidature_htmx,
    candidatures_list_htmx,
    documents_list_htmx,
    refresh_admissions_stats_htmx,
)

# Import des vues HTMX Finance
from .dashboards.htmx_finance import (
    validate_payment_htmx,
    reject_payment_htmx,
    create_cash_session_htmx,
    regenerate_code_htmx,
    mark_session_used_htmx,
    cancel_session_htmx,
    search_inscriptions_htmx,
    payment_detail_htmx,
    inscription_finance_detail_htmx,
    refresh_stats_htmx,
    payments_list_htmx,
)

# Import des exports
from .dashboards.exports import (
    export_candidatures_csv,
    export_payments_csv,
    export_executive_csv,
)
from .dashboards.manager_dashboard import *


from .dashboards.htmx_manager import *


app_name = "accounts"


urlpatterns = [

    # ==========================================================
    # AUTHENTIFICATION
    # ==========================================================
    path(
        "login/",
        PortalLoginView.as_view(),
        name="login",
    ),
    path(
        "logout/",
        auth_views.LogoutView.as_view(
            template_name="registration/logged_out.html"
        ),
        name="logout",
    ),
    path(
        "register/",
        register,
        name="register"
    ),


    # ==========================================================
    # DASHBOARDS PRINCIPAUX
    # ==========================================================
    path(
        "dashboard/",
        dashboard_redirect,
        name="dashboard_redirect"
    ),
    path(
        "dashboard/admissions/",
        admissions_dashboard,
        name="admissions_dashboard"
    ),
    path(
        "dashboard/finance/",
        finance_dashboard,
        name="finance_dashboard"
    ),
    path(
        "dashboard/executive/",
        executive_dashboard,
        name="executive_dashboard"
    ),


    # ==========================================================
    # PROFIL UTILISATEUR
    # ==========================================================
    path(
        "profile/",
        profile_detail,
        name="profile"
    ),
    path(
        "profile/edit/",
        edit_profile,
        name="edit_profile"
    ),
    path(
        "profile/email/",
        update_email,
        name="update_email"
    ),


    # ==========================================================
    # PROFIL - ONGLETS HTMX
    # ==========================================================
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


    # ==========================================================
    # HTMX - ADMISSIONS (Candidatures)
    # ==========================================================
    path(
        "htmx/candidature/<int:candidature_id>/detail/",
        get_candidature_detail_htmx,
        name="candidature_detail_htmx"
    ),
    path(
        "htmx/candidature/<int:candidature_id>/approve/",
        approve_candidature_htmx,
        name="approve_candidature_htmx"
    ),
    path(
        "htmx/candidature/<int:candidature_id>/reject/",
        reject_candidature_htmx,
        name="reject_candidature_htmx"
    ),
    path(
        "htmx/candidature/<int:candidature_id>/under-review/",
        set_candidature_under_review_htmx,
        name="set_candidature_under_review_htmx"
    ),
    path(
        "htmx/candidature/<int:candidature_id>/to-complete/",
        set_candidature_to_complete_htmx,
        name="set_candidature_to_complete_htmx"
    ),
    path(
        "htmx/candidature/<int:candidature_id>/create-inscription/",
        create_inscription_htmx,
        name="create_inscription_htmx"
    ),
    path(
        "htmx/candidature/<int:candidature_id>/delete/",
        delete_candidature_htmx,
        name="delete_candidature_htmx"
    ),


    # ==========================================================
    # HTMX - ADMISSIONS (Documents)
    # ==========================================================
    path(
        "htmx/document/<int:document_id>/validate/",
        validate_document_htmx,
        name="validate_document_htmx"
    ),


    # ==========================================================
    # HTMX - ADMISSIONS (Inscriptions)
    # ==========================================================
    path(
        "htmx/inscription/<int:inscription_id>/detail/",
        get_inscription_detail_htmx,
        name="inscription_detail_htmx"
    ),


    # ==========================================================
    # HTMX - ADMISSIONS (Listes & Stats)
    # ==========================================================
    path(
        "htmx/admissions/candidatures/",
        candidatures_list_htmx,
        name="candidatures_list_htmx"
    ),
    path(
        "htmx/admissions/documents/",
        documents_list_htmx,
        name="documents_list_htmx"
    ),
    path(
        "htmx/admissions/stats/",
        refresh_admissions_stats_htmx,
        name="refresh_admissions_stats_htmx"
    ),


    # ==========================================================
    # HTMX - FINANCE (Paiements)
    # ==========================================================
    path(
        "htmx/payment/<int:payment_id>/validate/",
        validate_payment_htmx,
        name="validate_payment_htmx"
    ),
    path(
        "htmx/payment/<int:payment_id>/reject/",
        reject_payment_htmx,
        name="reject_payment_htmx"
    ),
    path(
        "htmx/payment/<int:payment_id>/detail/",
        payment_detail_htmx,
        name="payment_detail_htmx"
    ),


    # ==========================================================
    # HTMX - FINANCE (Sessions Cash)
    # ==========================================================
    path(
        "htmx/cash-session/create/",
        create_cash_session_htmx,
        name="create_cash_session_htmx"
    ),
    path(
        "htmx/cash-session/<int:session_id>/regenerate/",
        regenerate_code_htmx,
        name="regenerate_code_htmx"
    ),
    path(
        "htmx/cash-session/<int:session_id>/complete/",
        mark_session_used_htmx,
        name="mark_session_used_htmx"
    ),
    path(
        "htmx/cash-session/<int:session_id>/cancel/",
        cancel_session_htmx,
        name="cancel_session_htmx"
    ),


    # ==========================================================
    # HTMX - FINANCE (Recherche & Détails)
    # ==========================================================
    path(
        "htmx/inscriptions/search/",
        search_inscriptions_htmx,
        name="search_inscriptions_htmx"
    ),
    path(
        "htmx/inscription/<int:inscription_id>/finance/",
        inscription_finance_detail_htmx,
        name="inscription_finance_detail_htmx"
    ),


    # ==========================================================
    # HTMX - FINANCE (Stats & Liste)
    # ==========================================================
    path(
        "htmx/finance/stats/",
        refresh_stats_htmx,
        name="refresh_stats_htmx"
    ),
    path(
        "htmx/finance/payments/",
        payments_list_htmx,
        name="payments_list_htmx"
    ),


    # ==========================================================
    # EXPORTS CSV
    # ==========================================================
    path(
        "export/candidatures/",
        export_candidatures_csv,
        name="export_candidatures_csv"
    ),
    path(
        "export/payments/",
        export_payments_csv,
        name="export_payments_csv"
    ),
    path(
        "export/executive/",
        export_executive_csv,
        name="export_executive_csv"
    ),
    # =============================================
    # MANAGER DASHBOARD
    # =============================================
    path("manager/", manager_dashboard, name="manager_dashboard"),
    path("manager/candidatures/", manager_candidatures, name="manager_candidatures"),
    path("manager/inscriptions/", manager_inscriptions, name="manager_inscriptions"),
    path("manager/paiements/", manager_paiements, name="manager_paiements"),

    # =============================================
    # HTMX ACTIONS - CANDIDATURES
    # =============================================
    path("htmx/manager/candidature/<int:pk>/detail/", candidature_detail, name="htmx_candidature_detail"),
    path("htmx/manager/candidature/<int:pk>/accept/", candidature_accept, name="htmx_candidature_accept"),
    path("htmx/manager/candidature/<int:pk>/reject/", candidature_reject, name="htmx_candidature_reject"),
    path("htmx/manager/candidature/<int:pk>/to-complete/", candidature_to_complete,
         name="htmx_candidature_to_complete"),

    # =============================================
    # HTMX ACTIONS - INSCRIPTIONS
    # =============================================
    path("htmx/manager/inscription/<int:pk>/detail/", inscription_detail, name="htmx_inscription_detail"),
    path("htmx/manager/inscription/<int:pk>/create/", inscription_create, name="htmx_inscription_create"),

    # =============================================
    # HTMX ACTIONS - PAIEMENTS
    # =============================================
    path("htmx/manager/payment/<int:pk>/detail/", payment_detail, name="htmx_payment_detail"),
    path("htmx/manager/payment/<int:pk>/validate/", payment_validate, name="htmx_payment_validate"),
    path("htmx/manager/payment/<int:pk>/cancel/", payment_cancel, name="htmx_payment_cancel"),

    # =============================================
    # HTMX ACTIONS - SESSIONS CASH GESTIONNAIRE
    # =============================================
    path("htmx/manager/inscription/<int:pk>/cash-session/create/", cash_session_create,
         name="htmx_manager_cash_session_create"),
    path("htmx/manager/cash-session/<int:pk>/regenerate/", cash_session_regenerate,
         name="htmx_manager_cash_session_regenerate"),
    path("htmx/manager/cash-session/<int:pk>/complete/", cash_session_complete,
         name="htmx_manager_cash_session_complete"),
    path("htmx/manager/cash-session/<int:pk>/cancel/", cash_session_cancel,
         name="htmx_manager_cash_session_cancel"),

    # =============================================
    # HTMX ACTIONS - SALAIRES GESTIONNAIRE
    # =============================================
    path("htmx/manager/salary/<int:pk>/detail/", salary_detail, name="htmx_manager_salary_detail"),
    path("htmx/manager/salary/<int:pk>/save/", salary_upsert, name="htmx_manager_salary_upsert"),
    path("htmx/manager/payroll/<int:pk>/pay/", salary_pay, name="htmx_manager_salary_pay"),
    path("htmx/manager/payroll/prepare-all/", salary_prepare_all, name="htmx_manager_salary_prepare_all"),
    path("htmx/manager/payroll/pay-ready-all/", salary_pay_ready_all, name="htmx_manager_salary_pay_ready_all"),

    # =============================================
    # HTMX ACTIONS - DEPENSES ET CAISSE GESTIONNAIRE
    # =============================================
    path("htmx/manager/expense/create/", expense_create, name="htmx_manager_expense_create"),
    path("htmx/manager/expense/<int:pk>/approve/", expense_approve, name="htmx_manager_expense_approve"),
    path("htmx/manager/expense/<int:pk>/reject/", expense_reject, name="htmx_manager_expense_reject"),
    path("htmx/manager/expense/<int:pk>/pay/", expense_pay, name="htmx_manager_expense_pay"),
    path("htmx/manager/cash-movement/create/", cash_movement_create, name="htmx_manager_cash_movement_create"),
    path("htmx/manager/cash/sync/", cash_sync, name="htmx_manager_cash_sync"),
    path("htmx/manager/cash-movement/<int:pk>/receipt/", cash_movement_receipt,
         name="htmx_manager_cash_movement_receipt"),

    # =============================================
    # RECHERCHE
    # =============================================
    path("htmx/manager/search/", global_search, name="htmx_search"),
]
