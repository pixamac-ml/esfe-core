# core/urls.py

from django.urls import path
from . import views


app_name = "core"

urlpatterns = [

    # =====================================================
    # PUBLIC PAGES
    # =====================================================

    path("", views.home, name="home"),
    path("apropos/", views.about, name="about"),
    path("contact/", views.contact_view, name="contact"),
    path("plan-du-site/", views.sitemap, name="sitemap"),
    path("robots.txt", views.robots_txt, name="robots_txt"),
    path("cookies/consent/", views.set_cookie_preferences, name="cookie_consent"),


    # =====================================================
    # LEGAL PAGES
    # =====================================================

    path("mentions-legales/", views.legal_notice, name="legal_notice"),
    path("confidentialite/", views.privacy_policy, name="privacy_policy"),
    path("conditions-utilisation/", views.terms_of_service, name="terms_of_service"),

    path(
        "legal/<str:page_type>/pdf/",
        views.legal_page_pdf,
        name="legal_pdf"
    ),

    # Apercu des pages d'erreur (dev/preprod)
    path("erreurs/<int:error_code>/", views.preview_error_page, name="error_page_preview"),


    # =====================================================
    # INTERNAL / SUPERADMIN
    # =====================================================


]