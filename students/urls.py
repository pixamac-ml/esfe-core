from django.urls import path

from .views import (
    class_attendance_summary_view,
    mark_student_attendance_view,
    mark_teacher_attendance_view,
    student_attendance_history_view,
)

app_name = "students"

urlpatterns = [
    path("attendance/student/mark/", mark_student_attendance_view, name="mark_student_attendance"),
    path("attendance/teacher/mark/", mark_teacher_attendance_view, name="mark_teacher_attendance"),
    path("attendance/class/<int:class_id>/summary/", class_attendance_summary_view, name="class_attendance_summary"),
    path("attendance/student/<int:student_id>/history/", student_attendance_history_view, name="student_attendance_history"),
]
