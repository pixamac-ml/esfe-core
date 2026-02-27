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


    # =====================================================
    # INTERNAL / SUPERADMIN
    # =====================================================


]