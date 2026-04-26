from django.urls import path
from .views import (
    ec_detail,
    dashboard,
    profile_partial,
    academics_partial,
    finance_partial,
    notifications_partial,
    student_courses,
)

app_name = "portal_student"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("profile/", profile_partial, name="profile_partial"),
    path("academics/", academics_partial, name="academics_partial"),
    path("finance/", finance_partial, name="finance_partial"),
    path("notifications/", notifications_partial, name="notifications_partial"),
    path("courses/", student_courses, name="student_courses"),
    path("courses/ec/<int:ec_id>/", ec_detail, name="ec_detail"),
]
