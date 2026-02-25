from django.urls import path
from .views import (
    NewsListView,
    NewsDetailView,
    ProgramDetailView,
    ProgramListView,
    ResultSessionListView,
)
from .views import event_list_view, event_detail_view

app_name = "news"

urlpatterns = [

    # LISTE ACTUALITÉS
    path("", NewsListView.as_view(), name="list"),

    # PORTAIL RÉSULTATS
    path("resultats/", ResultSessionListView.as_view(), name="result_list"),

    # PROGRAMMES
    path("programmes/", ProgramListView.as_view(), name="program_list"),
    path("programmes/<slug:slug>/", ProgramDetailView.as_view(), name="program_detail"),

    # GALERIES (AVANT LE SLUG GÉNÉRIQUE)
    path("galeries/", event_list_view, name="event_list"),
    path("galeries/<slug:slug>/", event_detail_view, name="event_detail"),

    # DÉTAIL ACTUALITÉ (TOUJOURS EN DERNIER)
    path("<slug:slug>/", NewsDetailView.as_view(), name="detail"),
]