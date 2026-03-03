from django.urls import path
from . import views

app_name = "community"

urlpatterns = [

    # ==========================
    # LISTING PRINCIPAL
    # ==========================
    path("", views.topic_list, name="topic_list"),

    # ==========================
    # LISTE MEMBRES ACTIFS
    # ==========================
    path("membres/", views.members_list, name="members_list"),

    # ==========================
    # PROFIL PUBLIC
    # ==========================
    path("membre/<str:username>/", views.public_profile, name="public_profile"),

    # ==========================
    # CRÉATION SUJET
    # ==========================
    path("nouveau/", views.create_topic, name="create_topic"),

    # ==========================
    # FILTRES
    # ==========================
    path("domaine/<slug:slug>/", views.topic_by_category, name="topic_by_category"),
    path("tag/<slug:slug>/", views.topic_by_tag, name="topic_by_tag"),

    # ==========================
    # SUJET
    # ==========================
    path("sujet/<slug:slug>/", views.topic_detail, name="topic_detail"),
    path("sujet/<slug:slug>/modifier/", views.edit_topic, name="edit_topic"),
    path("sujet/<slug:slug>/supprimer/", views.delete_topic, name="delete_topic"),

    # ==========================
    # ACTIONS HTMX
    # ==========================
    path("sujet/<slug:slug>/repondre/", views.add_answer, name="add_answer"),
    path("vote/<int:answer_id>/", views.vote_answer, name="vote_answer"),
]