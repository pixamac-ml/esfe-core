from django.urls import path

from .views import (
    class_attendance_summary_view,
    mark_student_attendance_view,
    mark_teacher_attendance_view,
    student_attendance_history_view,
)
from .views_carte import (
    card_pin_verify_view,
    card_scan_verify_view,
    carte_apercu_view,
    carte_pdf_view,
    portail_verification_view,
    portail_verify_token_view,
)

app_name = "students"

urlpatterns = [
    # Présence
    path("attendance/student/mark/", mark_student_attendance_view, name="mark_student_attendance"),
    path("attendance/teacher/mark/", mark_teacher_attendance_view, name="mark_teacher_attendance"),
    path("attendance/class/<int:class_id>/summary/", class_attendance_summary_view, name="class_attendance_summary"),
    path("attendance/student/<int:student_id>/history/", student_attendance_history_view, name="student_attendance_history"),

    # Carte étudiant
    path("carte/<int:carte_id>/apercu/", carte_apercu_view, name="carte_apercu"),
    path("carte/<int:carte_id>/pdf/", carte_pdf_view, name="carte_pdf"),

    # Portail de vérification public
    path("carte/verifier/", portail_verification_view, name="portail_verification"),
    path("carte/v/<str:token>/", portail_verify_token_view, name="portail_verify_token"),

    # Authentification par carte (HTMX)
    path("carte/scan/verify/", card_scan_verify_view, name="card_scan_verify"),
    path("carte/pin/verify/", card_pin_verify_view, name="card_pin_verify"),
]
