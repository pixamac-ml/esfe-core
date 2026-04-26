from django.urls import path
from .views import (
    courses_partial,
    ec_detail,
    dashboard,
    profile_partial,
    academics_partial,
    finance_partial,
    settings_partial,
    messages_partial,
    notifications_partial,
    student_courses,
    timetable_partial,
    update_settings_profile,
    upload_settings_document,
    update_content_progress,
)

app_name = "portal_student"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("profile/", profile_partial, name="profile_partial"),
    path("academics/", academics_partial, name="academics_partial"),
    path("finance/", finance_partial, name="finance_partial"),
    path("settings/", settings_partial, name="settings_partial"),
    path("notifications/", notifications_partial, name="notifications_partial"),
    path("partials/courses/", courses_partial, name="courses_partial"),
    path("partials/messages/", messages_partial, name="messages_partial"),
    path("partials/timetable/", timetable_partial, name="timetable_partial"),
    path("courses/", student_courses, name="student_courses"),
    path("courses/ec/<int:ec_id>/", ec_detail, name="ec_detail"),
    path("contents/<int:content_id>/progress/", update_content_progress, name="content_progress"),
    path("settings/profile/", update_settings_profile, name="update_settings_profile"),
    path("settings/documents/", upload_settings_document, name="upload_settings_document"),
]
