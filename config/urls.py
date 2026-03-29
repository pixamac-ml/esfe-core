"""
URL configuration for config project.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


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
    path("accounts/", include("django.contrib.auth.urls")),
    path("accounts/", include("accounts.urls")),
    #path("branches/", include("branches.urls")),
    # Applications métiers
    path("formations/", include("formations.urls")),
    path("blog/", include("blog.urls")),
    path("admissions/", include("admissions.urls")),
    path("inscriptions/", include("inscriptions.urls")),
    path("payments/", include("payments.urls")),
    path("actualites/", include("news.urls", namespace="news")),
    path('superadmin/', include('superadmin.urls')),
    # Core (home + pages publiques)
    path("", include("core.urls")),
    path("community/", include("community.urls")),
    # Dev only
    path("__reload__/", include("django_browser_reload.urls")),
    path("ckeditor5/", include("django_ckeditor_5.urls")),
]


# ==========================================================
# SERVIR LES MEDIA EN DÉVELOPPEMENT UNIQUEMENT
# ==========================================================

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )