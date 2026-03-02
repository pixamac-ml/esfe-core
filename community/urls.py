from django.urls import path
from . import views

app_name = "community"

urlpatterns = [

    # ==========================
    # LISTING PRINCIPAL
    # ==========================
    path("", views.topic_list, name="topic_list"),

    # ==========================
    # CRÉATION SUJET
    # ==========================
    path("nouveau/", views.create_topic, name="create_topic"),

    # ==========================
    # PAR DOMAINE (Category)
    # ==========================
    path("domaine/<slug:slug>/", views.topic_by_category, name="topic_by_category"),

    # ==========================
    # PAR TAG
    # ==========================
    path("tag/<slug:slug>/", views.topic_by_tag, name="topic_by_tag"),

    # ==========================
    # DÉTAIL SUJET
    # ==========================
    path("sujet/<slug:slug>/", views.topic_detail, name="topic_detail"),

    # ==========================
    # MODIFICATION SUJET
    # ==========================
    path("sujet/<slug:slug>/modifier/", views.edit_topic, name="edit_topic"),

    # ==========================
    # SUPPRESSION SUJET (POST)
    # ==========================
    path("sujet/<slug:slug>/supprimer/", views.delete_topic, name="delete_topic"),

    # ==========================
    # ACTIONS HTMX
    # ==========================
    path("sujet/<slug:slug>/repondre/", views.add_answer, name="add_answer"),
    path("vote/<int:answer_id>/", views.vote_answer, name="vote_answer"),
]