from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path

from core.sitemaps import build_sitemaps

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("portal/", include(("portal.urls", "accounts_portal"), namespace="accounts_portal")),
    path("formations/", include("formations.urls")),
    path("blog/", include("blog.urls")),
    path("admissions/", include("admissions.urls")),
    path("inscriptions/", include("inscriptions.urls")),
    path("payments/", include("payments.urls")),
    path("actualites/", include("news.urls", namespace="news")),
    path("superadmin/", include("superadmin.urls")),
    path("sitemap.xml", sitemap, {"sitemaps": build_sitemaps()}, name="sitemap_xml"),
    path("community/", include("community.urls")),
    path("ckeditor5/", include("django_ckeditor_5.urls")),
    path("", include(("core.urls", "core"), namespace="core")),
]

