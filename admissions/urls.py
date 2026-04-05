from django.urls import path
from . import views

app_name = "admissions"

urlpatterns = [
    path(
        "",
        views.admission_tunnel,
        name="admission_tunnel",
    ),
    path(
        "partials/step3/formations/",
        views.admission_step3_formations,
        name="admission_step3_formations",
    ),
    path(
        "partials/step3/documents/",
        views.admission_step3_documents,
        name="admission_step3_documents",
    ),
    path(
        "done/<int:candidature_id>/",
        views.admission_done,
        name="done",
    ),
    path(
        "s-inscrire/<slug:slug>/",
        views.apply_to_programme,
        name="apply"
    ),

    path(
        "confirmation/<int:candidature_id>/",
        views.candidature_confirmation,
        name="confirmation"
    ),

]
