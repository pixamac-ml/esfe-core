from django.urls import path
from . import views

app_name = "payments"

urlpatterns = [
    # ============================================
    # PAIEMENTS
    # ============================================

    # Initier un paiement (HTMX)
    path(
        "initier/<str:token>/",
        views.student_initiate_payment,
        name="student_initiate",
    ),

    # Vérification agent en temps réel (HTMX)
    path(
        "verify-agent/<str:token>/",
        views.verify_agent,
        name="verify_agent",
    ),

    # Initier session espèces (HTMX)
    path(
        "cash-session/<str:token>/",
        views.initiate_cash_session,
        name="initiate_cash_session",
    ),

    # Rafraîchir le block financier (HTMX)
    path(
        "refresh/<str:token>/",
        views.refresh_finance,
        name="refresh_finance",
    ),

    # ============================================
    # REÇUS
    # ============================================

    # Détail reçu
    path(
        "receipt/<str:receipt_number>/",
        views.receipt_public_detail,
        name="receipt_detail",
    ),

    # Télécharger PDF reçu
    path(
        "receipt/<str:receipt_number>/pdf/",
        views.receipt_pdf,
        name="receipt_pdf",
    ),

    # ============================================
    # API
    # ============================================

    # Liste agents pour autocomplétion
    path(
        "api/agents/",
        views.agents_list,
        name="agents_list",
    ),

    # Statut paiement (pour polling)
    path(
        "api/status/<str:token>/",
        views.payment_status,
        name="payment_status",
    ),
]


