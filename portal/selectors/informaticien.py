from __future__ import annotations

from django.db.models import Count, Q

from academics.models import AcademicClass, AcademicEnrollment, AcademicYear, EC, ECGrade
from portal.models import SupportAuditLog, SupportTicket


def support_tickets_for_branch(*, branch, status=""):
    queryset = SupportTicket.objects.select_related(
        "branch",
        "requester_user",
        "assigned_to",
        "created_by",
        "resolved_by",
    )
    if branch:
        queryset = queryset.filter(branch=branch)
    if status:
        queryset = queryset.filter(status=status)
    return queryset.order_by("-created_at", "-id")


def audit_logs_for_branch(*, branch):
    queryset = SupportAuditLog.objects.select_related("actor", "target_user", "branch")
    if branch:
        queryset = queryset.filter(branch=branch)
    return queryset.order_by("-created_at", "-id")


def academic_classes_for_branch(*, branch):
    queryset = (
        AcademicClass.objects.select_related("programme", "branch", "academic_year")
        .prefetch_related("semesters")
        .filter(is_archived=False)
        .annotate(effectif=Count("enrollments", filter=Q(enrollments__is_active=True), distinct=True))
    )
    if branch:
        queryset = queryset.filter(branch=branch)
    return queryset.order_by("programme__title", "level")


def active_academic_year():
    return AcademicYear.objects.filter(is_active=True).first()


def classes_without_notes_for_branch(*, branch):
    queryset = academic_classes_for_branch(branch=branch).filter(is_active=True)
    return queryset.exclude(enrollments__ec_grades__isnull=False).distinct()


def ecs_without_schedule_teacher_for_branch(*, branch):
    queryset = EC.objects.select_related("ue", "ue__semester", "ue__semester__academic_class").filter(
        ue__semester__academic_class__is_active=True
    )
    if branch:
        queryset = queryset.filter(ue__semester__academic_class__branch=branch)
    return queryset.exclude(schedule_events__teacher__isnull=False).distinct().order_by(
        "ue__semester__academic_class__programme__title",
        "ue__semester__academic_class__level",
        "title",
    )


def enrollments_without_grades_for_branch(*, branch):
    queryset = AcademicEnrollment.objects.select_related("student", "academic_class", "branch").filter(is_active=True)
    if branch:
        queryset = queryset.filter(branch=branch)
    return queryset.filter(ec_grades__isnull=True).distinct()


def grade_entries_for_class(*, academic_class):
    return ECGrade.objects.select_related("enrollment", "ec", "ec__ue").filter(
        enrollment__academic_class=academic_class
    )
