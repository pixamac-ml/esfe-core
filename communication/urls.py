from django.urls import path

from . import views

app_name = "communication"

urlpatterns = [
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/partial/", views.notifications_partial, name="notifications_partial"),
    path("notifications/<int:pk>/read/", views.mark_notification_read, name="mark_notification_read"),
    path("notifications/read-all/", views.mark_all_notifications_read, name="mark_all_notifications_read"),
]
