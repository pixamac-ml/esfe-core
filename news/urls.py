from django.urls import path
from .views import (
    NewsListView,
    NewsListFragmentView,
    NewsSidebarFragmentView,
    NewsPollingView,
    NewsDetailView,
    ProgramDetailView,
    ProgramListView,
    ResultSessionListView,
    ResultSessionListFragmentView,
    ResultSessionPollingView,
)
from .views import event_list_view, event_detail_view

app_name = "news"

urlpatterns = [

    # HTMX NEWS (DOIT ETRE AVANT LE SLUG)
    path("_htmx/list/", NewsListFragmentView.as_view(), name="list_fragment"),
    path("_htmx/sidebar/", NewsSidebarFragmentView.as_view(), name="sidebar_fragment"),
    path("_htmx/poll/", NewsPollingView.as_view(), name="poll"),

    # LISTE ACTUALITÉS
    path("", NewsListView.as_view(), name="list"),

    # PORTAIL RÉSULTATS
    path("resultats/", ResultSessionListView.as_view(), name="result_list"),
    path("resultats/_htmx/list/", ResultSessionListFragmentView.as_view(), name="result_list_fragment"),
    path("resultats/_htmx/poll/", ResultSessionPollingView.as_view(), name="result_poll"),

    # PROGRAMMES
    path("programmes/", ProgramListView.as_view(), name="program_list"),
    path("programmes/<slug:slug>/", ProgramDetailView.as_view(), name="program_detail"),

    # GALERIES (AVANT LE SLUG GÉNÉRIQUE)
    path("galeries/", event_list_view, name="event_list"),
    path("galeries/<slug:slug>/", event_detail_view, name="event_detail"),

    # DÉTAIL ACTUALITÉ (TOUJOURS EN DERNIER)
    path("<slug:slug>/", NewsDetailView.as_view(), name="detail"),
]