from django.urls import path

from portal.views import (
    portal_dashboard,
    portal_home,
    staff_portal,
    student_portal,
    teacher_portal,
)


app_name = "accounts_portal"


urlpatterns = [
    path("", portal_home, name="portal_home"),
    path("dashboard/", portal_dashboard, name="portal_dashboard"),
    path("student/", student_portal, name="portal_student"),
    path("staff/", staff_portal, name="portal_staff"),
    path("teacher/", teacher_portal, name="portal_teacher"),
]

