"""
URL configuration for config project.
"""

from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from core import views as core_views
from core.sitemaps import build_sitemaps


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
    path("admin/", admin.site.urls),
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
    path("shop/", include("shop.urls")),
    path("actualites/", include("news.urls", namespace="news")),
    path('superadmin/', include('superadmin.urls')),
    path("secretary/", include("secretary.urls")),
    path("students/", include("students.urls")),
    path("sitemap.xml", sitemap, {"sitemaps": build_sitemaps()}, name="sitemap_xml"),
    # Core (home + pages publiques)
    path("", include("core.urls")),
    path("academics/", include("academics.urls")),
    path("community/", include("community.urls")),
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

# Fallback final: toute URL non resolue renvoie la page 404 specialisee.
urlpatterns += [
    re_path(r"^(?P<unmatched_path>.*)$", core_views.fallback_404, name="fallback_404"),
]
