from django.urls import path

from . import views

app_name = "notification_center"

urlpatterns = [
    path("", views.notifications, name="notifications"),
    path("widget/", views.notifications_widget, name="notifications_widget"),
    path("partial/", views.notifications_partial, name="notifications_partial"),
    path("<int:pk>/detail/", views.notification_detail, name="notification_detail"),
    path("<int:pk>/read/", views.mark_notification_read, name="mark_notification_read"),
    path("<int:pk>/unread/", views.mark_notification_unread, name="mark_notification_unread"),
    path("read-all/", views.mark_all_notifications_read, name="mark_all_notifications_read"),
]
