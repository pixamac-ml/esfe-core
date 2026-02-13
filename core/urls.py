# core/urls.py
from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("mentions-legales/", views.legal_notice, name="legal_notice"),
    path("confidentialite/", views.privacy_policy, name="privacy_policy"),
    path("conditions-utilisation/", views.terms_of_service, name="terms_of_service"),
    path("plan-du-site/", views.sitemap, name="sitemap"),
    path("legal/<str:page_type>/pdf/", views.legal_page_pdf, name="legal_pdf"),
    # ✅ AJOUTE ÇA
    path("legal/<str:page_type>/pdf/", views.legal_page_pdf, name="legal_pdf"),
]
