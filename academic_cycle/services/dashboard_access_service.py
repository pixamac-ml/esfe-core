from django.utils import timezone

from academic_cycle import constants
from academic_cycle.models import AcademicReEnrollment, StudentAccessPolicy
from academic_cycle.services.financial_policy_service import compute_student_financial_position


def compute_student_access_policy(student, academic_year):
    position = compute_student_financial_position(student, academic_year)
    reenrollment = AcademicReEnrollment.objects.filter(student=student, target_academic_year=academic_year).first()
    has_active_enrollment = student.user.academic_enrollments.filter(academic_year=academic_year, is_active=True).exists()

    access_level = constants.ACCESS_FULL if has_active_enrollment else constants.ACCESS_REENROLLMENT_REQUIRED
    reason = "Acces complet."
    can_courses = has_active_enrollment
    can_schedule = has_active_enrollment

    if reenrollment and reenrollment.status != AcademicReEnrollment.STATUS_ACTIVATED:
        access_level = constants.ACCESS_REENROLLMENT_REQUIRED
        reason = "Reinscription a finaliser."
        can_courses = False
        can_schedule = False

    documents_allowed = position.remaining_amount <= 0
    if not documents_allowed and access_level == constants.ACCESS_FULL:
        access_level = constants.ACCESS_LIMITED
        reason = "Documents verrouilles jusqu'a regularisation financiere."

    policy, _ = StudentAccessPolicy.objects.update_or_create(
        student=student,
        academic_year=academic_year,
        defaults={
            "branch": position.branch,
            "access_level": access_level,
            "can_access_dashboard": True,
            "can_access_courses": can_courses,
            "can_access_schedule": can_schedule,
            "can_download_bulletin": documents_allowed,
            "can_download_transcript": documents_allowed,
            "can_download_certificate": documents_allowed,
            "can_download_diploma": documents_allowed,
            "reason": reason,
            "computed_at": timezone.now(),
        },
    )
    return policy


def apply_student_access_policy(student, policy):
    return policy


def can_download_bulletin(student, academic_year):
    return compute_student_access_policy(student, academic_year).can_download_bulletin


def can_download_diploma(student):
    active_year = student.user.academic_enrollments.filter(is_active=True).order_by("-academic_year__start_date").first()
    if not active_year:
        return False
    return compute_student_access_policy(student, active_year.academic_year).can_download_diploma
