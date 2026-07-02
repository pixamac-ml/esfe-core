from django.urls import path
from . import views

app_name = "ui"

urlpatterns = [
    path("galerie/", views.gallery, name="gallery"),
]
