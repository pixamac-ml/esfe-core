from django.urls import path
from . import views

app_name = "community"

urlpatterns = [
    path("", views.topic_list, name="topic_list"),
    path("categorie/<slug:slug>/", views.topic_by_category, name="topic_by_category"),
    path("topic/<slug:slug>/", views.topic_detail, name="topic_detail"),
    path("topic/<slug:slug>/repondre/", views.add_answer, name="add_answer"),
    path("vote/<int:answer_id>/", views.vote_answer, name="vote_answer"),
]