"""
URL configuration for config project.
"""

from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse
from core import views as core_views
from core.sitemaps import build_sitemaps
from portal.views.it_surveillance import surveillance_general_api_view


# ==========================================================
# HANDLERS GLOBAUX D’ERREURS (production uniquement)
# ==========================================================

handler404 = "core.views.custom_404"
handler403 = "core.views.custom_403"
handler500 = "core.views.custom_500"
handler400 = "core.views.custom_400"


# ==========================================================
# URL PATTERNS
# ==========================================================

urlpatterns = [

    # Admin Django (protégé par défaut)
    path("favicon.ico", lambda request: HttpResponse(status=204), name="favicon_ico"),
    path("admin/", admin.site.urls),
    path("surveillance/general/", surveillance_general_api_view, name="surveillance_general_api"),
    path("accounts/", include("accounts.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("portal/student-dashboard/", include("portal.student.urls")),
    path("portal/", include(("portal.urls", "accounts_portal"), namespace="accounts_portal")),
    #path("branches/", include("branches.urls")),
    # Applications métiers
    path("formations/", include("formations.urls")),
    path("blog/", include("blog.urls")),
    path("admissions/", include("admissions.urls")),
    path("inscriptions/", include("inscriptions.urls")),
    path("payments/", include("payments.urls")),
    path("academic-cycle/", include("academic_cycle.urls")),
    path("shop/", include(("shop.urls", "shop"), namespace="shop")),
    path("actualites/", include("news.urls", namespace="news")),
    path('superadmin/', include('superadmin.urls')),
    path("secretary/", include("secretary.urls")),
    path("students/", include("students.urls")),
    path("sitemap.xml", sitemap, {"sitemaps": build_sitemaps()}, name="sitemap_xml"),
    # Core (home + pages publiques)
    path("", include("core.urls")),
    path("academics/", include("academics.urls")),
    path("community/", include("community.urls")),
    path("communication/", include(("communication.urls", "communication"), namespace="communication")),
    path("marketing/", include(("marketing.urls", "marketing"), namespace="marketing")),
    path("ckeditor5/", include("django_ckeditor_5.urls")),
]

if settings.DEBUG and "django_browser_reload" in settings.INSTALLED_APPS:
    urlpatterns.append(path("__reload__/", include("django_browser_reload.urls")))


# ==========================================================
# SERVIR LES MEDIA EN DÉVELOPPEMENT UNIQUEMENT
# ==========================================================

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )

# Les URLs non resolues sont gérées par handler404 (custom_404).
