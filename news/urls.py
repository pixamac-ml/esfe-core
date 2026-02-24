from django.urls import path
from .views import (
    NewsListView,
    NewsDetailView,
    ProgramDetailView,
    ProgramListView,
    ResultSessionListView,
)

app_name = "news"

urlpatterns = [

    # LISTE ACTUALITÉS
    path("", NewsListView.as_view(), name="list"),

    # PORTAIL RÉSULTATS
    path("resultats/", ResultSessionListView.as_view(), name="result_list"),

    # PROGRAMMES
    path("programmes/", ProgramListView.as_view(), name="program_list"),
    path("programmes/<slug:slug>/", ProgramDetailView.as_view(), name="program_detail"),

    # DÉTAIL ACTUALITÉ (TOUJOURS EN DERNIER)
    path("<slug:slug>/", NewsDetailView.as_view(), name="detail"),
]