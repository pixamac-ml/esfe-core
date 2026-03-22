from django.urls import path
from . import views

app_name = "community"

urlpatterns = [
    # ======================================================
    # LISTING PRINCIPAL
    # ======================================================
    path("", views.topic_list, name="topic_list"),

    # ======================================================
    # CLASSEMENT (GAMIFICATION)
    # ======================================================
    path("classement/", views.leaderboard, name="leaderboard"),

    # ======================================================
    # MEMBRES / COMMUNAUTÉ
    # ======================================================
    path("membres/", views.members_list, name="members_list"),

    # ======================================================
    # ACCEPTER RÉPONSE
    # ======================================================
    path("answer/<int:answer_id>/accept/", views.accept_answer, name="accept_answer"),

    # ======================================================
    # PROFIL UTILISATEUR
    # ======================================================
    path("membre/<str:username>/", views.public_profile, name="public_profile"),

    # ======================================================
    # PROFIL — PARTIALS HTMX
    # ======================================================
    path("membre/<str:username>/activity/", views.profile_activity, name="profile_activity"),
    path("membre/<str:username>/answers/", views.profile_answers, name="profile_answers"),
    path("membre/<str:username>/topics/", views.profile_topics, name="profile_topics"),
    path("membre/<str:username>/badges/", views.profile_badges, name="profile_badges"),

    # ======================================================
    # NOTIFICATIONS
    # ======================================================
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/partial/", views.notifications_partial, name="notifications_partial"),
    path("notifications/<int:pk>/read/", views.mark_notification_read, name="mark_notification_read"),
    path("notifications/read-all/", views.mark_all_notifications_read, name="mark_all_notifications_read"),
    path("notifications/<int:pk>/delete/", views.delete_notification, name="delete_notification"),
    path("notifications/unread-count/", views.notifications_unread_count, name="notifications_unread_count"),

    # ======================================================
    # CRÉATION SUJET
    # ======================================================
    path("nouveau/", views.create_topic, name="create_topic"),

    # ======================================================
    # FILTRES
    # ======================================================
    path("domaine/<slug:slug>/", views.topic_by_category, name="topic_by_category"),
    path("tag/<slug:slug>/", views.topic_by_tag, name="topic_by_tag"),

    # ======================================================
    # ABONNEMENTS AUX DOMAINES
    # ======================================================
    path("domaine/<slug:slug>/abonner/", views.subscribe_category, name="subscribe_category"),
    path("domaine/<slug:slug>/desabonner/", views.unsubscribe_category, name="unsubscribe_category"),
    path("mes-abonnements/", views.my_subscriptions, name="my_subscriptions"),

    # ======================================================
    # SUJET
    # ======================================================
    path("sujet/<slug:slug>/", views.topic_detail, name="topic_detail"),
    path("sujet/<slug:slug>/modifier/", views.edit_topic, name="edit_topic"),
    path("sujet/<slug:slug>/supprimer/", views.delete_topic, name="delete_topic"),

    # ======================================================
    # ACTIONS HTMX
    # ======================================================
    path("sujet/<slug:slug>/repondre/", views.add_answer, name="add_answer"),
    path("vote/<int:answer_id>/", views.vote_answer, name="vote_answer"),

    # ======================================================
    # SIGNALEMENTS
    # ======================================================
    path("sujet/<slug:slug>/signaler/", views.report_topic, name="report_topic"),
    path("answer/<int:answer_id>/signaler/", views.report_answer, name="report_answer"),

    # ======================================================
    # MODÉRATION
    # ======================================================
    path("sujet/<slug:slug>/lock/", views.lock_topic, name="lock_topic"),
    path("sujet/<slug:slug>/moderate/delete/", views.moderate_delete_topic, name="moderate_delete_topic"),
    path("answer/<int:answer_id>/moderate/delete/", views.moderate_delete_answer, name="moderate_delete_answer"),
]