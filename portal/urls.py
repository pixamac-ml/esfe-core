from django.urls import path

from portal.views import (
    admin_grade_dashboard,
    load_grades_table,
    load_student_results,
    publish_semester_view,
    save_grade,
)
from portal.views.admin_grades import excel_grade_view
from portal.views.views import (
    admissions_portal,
    director_portal,
    finance_portal,
    it_portal,
    portal_dashboard,
    portal_home,
    secretary_portal,
    staff_portal,
    student_portal,
    supervisor_mark_student_attendance,
    supervisor_mark_teacher_attendance,
    supervisor_portal,
    supervisor_save_lesson_log,
    teacher_portal,
)

app_name = "accounts_portal"

urlpatterns = [
    path("", portal_home, name="portal_home"),
    path("dashboard/", portal_dashboard, name="portal_dashboard"),
    path("student/", student_portal, name="portal_student"),
    path("staff/", staff_portal, name="portal_staff"),
    path("teacher/", teacher_portal, name="portal_teacher"),
    path("finance/", finance_portal, name="portal_finance"),
    path("secretary/", secretary_portal, name="portal_secretary"),
    path("admissions/", admissions_portal, name="portal_admissions"),
    path("director/", director_portal, name="portal_director"),
    path("supervisor/", supervisor_portal, name="portal_supervisor"),
    path("it/", it_portal, name="portal_it"),
    path(
        "supervisor/actions/student-attendance/",
        supervisor_mark_student_attendance,
        name="supervisor_mark_student_attendance",
    ),
    path(
        "supervisor/actions/teacher-attendance/",
        supervisor_mark_teacher_attendance,
        name="supervisor_mark_teacher_attendance",
    ),
    path(
        "supervisor/actions/lesson-log/",
        supervisor_save_lesson_log,
        name="supervisor_save_lesson_log",
    ),
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
