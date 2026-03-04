from django.urls import path
from . import views

app_name = "community"


urlpatterns = [

    # ======================================================
    # LISTING PRINCIPAL
    # ======================================================
    path(
        "",
        views.topic_list,
        name="topic_list"
    ),

    # ======================================================
    # MEMBRES / COMMUNAUTÉ
    # ======================================================
    path(
        "membres/",
        views.members_list,
        name="members_list"
    ),

    # ======================================================
    # PROFIL UTILISATEUR
    # ======================================================
    path(
        "membre/<str:username>/",
        views.public_profile,
        name="public_profile"
    ),

    # ======================================================
    # PROFIL — PARTIALS HTMX
    # ======================================================
    path(
        "membre/<str:username>/activity/",
        views.profile_activity,
        name="profile_activity"
    ),

    path(
        "membre/<str:username>/answers/",
        views.profile_answers,
        name="profile_answers"
    ),

    path(
        "membre/<str:username>/topics/",
        views.profile_topics,
        name="profile_topics"
    ),

    path(
        "membre/<str:username>/badges/",
        views.profile_badges,
        name="profile_badges"
    ),

    # ======================================================
    # NOTIFICATIONS
    # ======================================================
    path(
        "notifications/",
        views.notifications,
        name="notifications"
    ),

    # ======================================================
    # CRÉATION SUJET
    # ======================================================
    path(
        "nouveau/",
        views.create_topic,
        name="create_topic"
    ),

    # ======================================================
    # FILTRES
    # ======================================================
    path(
        "domaine/<slug:slug>/",
        views.topic_by_category,
        name="topic_by_category"
    ),

    path(
        "tag/<slug:slug>/",
        views.topic_by_tag,
        name="topic_by_tag"
    ),

    # ======================================================
    # SUJET
    # ======================================================
    path(
        "sujet/<slug:slug>/",
        views.topic_detail,
        name="topic_detail"
    ),

    path(
        "sujet/<slug:slug>/modifier/",
        views.edit_topic,
        name="edit_topic"
    ),

    path(
        "sujet/<slug:slug>/supprimer/",
        views.delete_topic,
        name="delete_topic"
    ),

    # ======================================================
    # ACTIONS HTMX
    # ======================================================
    path(
        "sujet/<slug:slug>/repondre/",
        views.add_answer,
        name="add_answer"
    ),

    path(
        "vote/<int:answer_id>/",
        views.vote_answer,
        name="vote_answer"
    ),
]