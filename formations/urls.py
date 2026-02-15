from django.urls import path
from . import views

app_name = "formations"

urlpatterns = [
    path("", views.formation_list, name="list"),

    path("<slug:slug>/", views.formation_detail, name="detail"),
]
