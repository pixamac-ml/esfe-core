from django.urls import path
from .views import apply_to_programme,candidature_confirmation

app_name = "admissions"

urlpatterns = [
    path(
        "s-inscrire/<slug:slug>/",
        apply_to_programme,
        name="apply"
    ),

    path(
        "confirmation/<int:candidature_id>/",
        candidature_confirmation,
        name="confirmation"
    ),

]
