from .create_student import create_student_after_first_payment
from .attendance_service import (
    detect_repeated_absences,
    detect_repeated_lates,
    get_class_attendance_summary,
    get_student_attendance_history,
    mark_student_attendance,
    mark_teacher_attendance,
)

__all__ = [
    "create_student_after_first_payment",
    "mark_student_attendance",
    "mark_teacher_attendance",
    "get_class_attendance_summary",
    "get_student_attendance_history",
    "detect_repeated_absences",
    "detect_repeated_lates",
]
