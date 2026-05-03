from __future__ import annotations

from django.db.models import Count, QuerySet

from academics.models import AcademicClass, Semester
from students.models import Student


def get_it_academic_classes(*, branch) -> QuerySet[AcademicClass]:
    queryset = (
        AcademicClass.objects.select_related("programme", "branch", "academic_year")
        .filter(is_active=True)
        .annotate(student_count=Count("enrollments", distinct=True))
        .order_by("branch__name", "level", "programme__title")
    )
    if branch:
        queryset = queryset.filter(branch=branch)
    return queryset


def get_it_semesters_for_class(*, academic_class) -> QuerySet[Semester]:
    return (
        Semester.objects.select_related("academic_class", "academic_class__branch")
        .filter(academic_class=academic_class)
        .order_by("number")
    )


def get_it_students_for_class(*, academic_class):
    queryset = Student.objects.select_related(
        "user",
        "inscription__candidature__branch",
        "inscription__candidature__programme",
    )
    if academic_class:
        queryset = queryset.filter(user__academic_enrollments__academic_class=academic_class)
    return queryset.distinct().order_by(
        "inscription__candidature__last_name",
        "inscription__candidature__first_name",
        "matricule",
    )
