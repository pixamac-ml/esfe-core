from django.urls import path
from .views import NewsListView, NewsDetailView, ProgramDetailView, ProgramListView

app_name = "news"

urlpatterns = [
    path(
        "",
        NewsListView.as_view(),
        name="list"
    ),
    path(
        "<slug:slug>/",
        NewsDetailView.as_view(),
        name="detail"
    ),

    path("programmes/", ProgramListView.as_view(), name="program_list"),

    path("programmes/<slug:slug>/", ProgramDetailView.as_view(), name="program_detail"),
]
