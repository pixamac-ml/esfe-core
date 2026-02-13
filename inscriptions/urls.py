# inscriptions/urls.py

from django.urls import path
from .views import inscription_public_detail

app_name = "inscriptions"

urlpatterns = [
    path(
        "dossier/<str:token>/",
        inscription_public_detail,
        name="public_detail"
    ),
]
