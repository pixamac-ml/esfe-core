from django.urls import path
from . import views

app_name = "formations"

urlpatterns = [
    path("", views.formation_list, name="list"),
    path("fragment/", views.formation_list_fragment, name="list_fragment"),
    path("<slug:slug>/", views.formation_detail, name="detail"),
]
