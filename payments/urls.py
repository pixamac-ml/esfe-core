from django.urls import path
from . import views

app_name = "payments"

urlpatterns = [
    path(
        "initier/<str:token>/",
        views.student_initiate_payment,
        name="student_initiate",
    ),
    path(
        "receipt/<str:receipt_number>/pdf/",
        views.receipt_pdf,
        name="receipt_pdf",
    ),

    path(
        "verify-agent/",
        views.verify_agent_ajax,
        name="verify_agent_ajax"
    ),

    path(
        "cash-session/<str:token>/",
        views.initiate_cash_session,
        name="initiate_cash_session",
    ),

]
