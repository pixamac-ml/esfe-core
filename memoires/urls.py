from django.urls import path

from . import views

app_name = "memoires"

urlpatterns = [
    path("", views.MemoireListView.as_view(), name="liste"),
    path("<slug:slug>/", views.MemoireDetailView.as_view(), name="detail"),
    path("<slug:slug>/page/<int:numero>/", views.servir_page, name="page"),
]
