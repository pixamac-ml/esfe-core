from django.urls import path

from . import views

app_name = "memoires"

urlpatterns = [
    path("", views.MemoireListView.as_view(), name="liste"),
    path("favoris/", views.favoris_liste, name="favoris"),
    path("<slug:slug>/", views.MemoireDetailView.as_view(), name="detail"),
    path("<slug:slug>/page/<int:numero>/", views.servir_page, name="page"),
    path("<slug:slug>/favori/", views.toggle_favori, name="toggle_favori"),
]
