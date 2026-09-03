from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Exists, OuterRef, Q, Sum

from academics.models import EC, ECGrade, AcademicClass, Semester, UE


def get_class_full_structure(academic_class):
    return (
        AcademicClass.objects.filter(pk=academic_class.pk)
        .select_related("programme", "branch", "academic_year")
        .prefetch_related("semesters__ues__ecs")
        .first()
    )


def get_ues_by_semester(semester):
    return UE.objects.filter(semester=semester).exclude(structure_status=UE.STRUCTURE_ARCHIVED).order_by("code", "id")


def get_ecs_by_ue(ue):
    return EC.objects.filter(ue=ue).exclude(structure_status=EC.STRUCTURE_ARCHIVED).order_by("id")


def semester_has_active_ecs(semester):
    """Whether a semester exposes at least one non-archived subject."""
    return EC.objects.filter(ue__semester=semester).exclude(
        structure_status=EC.STRUCTURE_ARCHIVED
    ).exists()


def get_total_credits_by_semester(semester):
    total = (
        EC.objects.filter(ue__semester=semester)
        .exclude(structure_status=EC.STRUCTURE_ARCHIVED)
        .aggregate(total=Sum("credit_required"))["total"]
    )
    return total or Decimal("0.00")


def get_semester_completeness_state(semester):
    active_ues = get_ues_by_semester(semester)
    active_ecs = EC.objects.filter(ue__semester=semester).exclude(structure_status=EC.STRUCTURE_ARCHIVED)
    total_credits = get_total_credits_by_semester(semester)
    missing_teacher_count = get_ecs_without_teacher(semester=semester).count()
    incomplete_ues_count = get_incomplete_ues(semester=semester).count()

    blocking_reasons = []
    if not active_ues.exists():
        blocking_reasons.append("Aucune UE configuree.")
    if not active_ecs.exists():
        blocking_reasons.append("Aucun EC configure.")
    if total_credits != semester.total_required_credits:
        blocking_reasons.append("Credits semestre incoherents.")
    if missing_teacher_count:
        blocking_reasons.append(f"{missing_teacher_count} EC sans enseignant.")
    if incomplete_ues_count:
        blocking_reasons.append(f"{incomplete_ues_count} UE incomplete(s).")

    return {
        "semester": semester,
        "required_credits": semester.total_required_credits,
        "configured_credits": total_credits,
        "ue_count": active_ues.count(),
        "ec_count": active_ecs.count(),
        "missing_teacher_count": missing_teacher_count,
        "incomplete_ues_count": incomplete_ues_count,
        "is_complete": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
    }


def get_ecs_without_teacher(*, semester=None, academic_class=None):
    queryset = EC.objects.exclude(structure_status=EC.STRUCTURE_ARCHIVED)
    if semester is not None:
        queryset = queryset.filter(ue__semester=semester)
    if academic_class is not None:
        queryset = queryset.filter(ue__semester__academic_class=academic_class)
    return queryset.annotate(
        active_assignments=Count(
            "director_teacher_assignments",
            filter=Q(director_teacher_assignments__is_active=True),
        )
    ).filter(active_assignments=0)


def get_ecs_without_grade(*, semester=None, academic_class=None):
    queryset = EC.objects.exclude(structure_status=EC.STRUCTURE_ARCHIVED)
    if semester is not None:
        queryset = queryset.filter(ue__semester=semester)
    if academic_class is not None:
        queryset = queryset.filter(ue__semester__academic_class=academic_class)
    grade_exists = ECGrade.objects.filter(ec=OuterRef("pk"))
    return queryset.annotate(has_grade=Exists(grade_exists)).filter(has_grade=False)


def get_incomplete_ues(*, semester=None, academic_class=None):
    queryset = UE.objects.exclude(structure_status=UE.STRUCTURE_ARCHIVED)
    if semester is not None:
        queryset = queryset.filter(semester=semester)
    if academic_class is not None:
        queryset = queryset.filter(semester__academic_class=academic_class)
    return queryset.annotate(
        active_ec_count=Count("ecs", filter=~Q(ecs__structure_status=EC.STRUCTURE_ARCHIVED))
    ).filter(active_ec_count=0)
