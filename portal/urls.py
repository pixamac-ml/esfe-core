from django.urls import path

from portal.views import (

    admin_grade_dashboard,
    load_student_results,
    load_grades_table,
    publish_semester_view,
    save_grade,
)
from portal.views.admin_grades import excel_grade_view
from portal.views.views import (
    portal_dashboard,
    portal_home,
    staff_portal,
    student_portal,
    teacher_portal,
)
app_name = "accounts_portal"

urlpatterns = [
    path("", portal_home, name="portal_home"),

    # 🔥 DASHBOARD PRINCIPAL
    path("dashboard/", portal_dashboard, name="portal_dashboard"),

    # 🔥 DASHBOARD PAR ROLE
    path("student/", student_portal, name="portal_student"),
    path("staff/", staff_portal, name="portal_staff"),
    path("teacher/", teacher_portal, name="portal_teacher"),

    # 🔥 SYSTEME NOTES
    path("admin/grades/", admin_grade_dashboard, name="admin_grade_dashboard"),
    path("admin/grades/<int:enrollment_id>/", load_student_results, name="load_student_results"),
    path("admin/grades/<int:enrollment_id>/<int:semester_id>/", load_grades_table, name="load_grades_table"),
    path("admin/grades/save/", save_grade, name="save_grade"),
    path(
        "admin/grades/<int:enrollment_id>/<int:semester_id>/publish/",
        publish_semester_view,
        name="publish_semester",
    ),

    path(
        "admin/grades/excel/<int:enrollment_id>/<int:semester_id>/",
        excel_grade_view,
        name="excel_grade_view",
    ),
]
