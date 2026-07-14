from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum

from academics.models import AcademicClass, EC, Semester, UE
from portal.models import DirectorTeacherAssignment


def _assignment_queryset(*, branch=None, teacher=None, academic_class=None, semester=None, ue=None, ec=None, active_only=True):
    queryset = DirectorTeacherAssignment.objects.select_related(
        "teacher",
        "branch",
        "academic_class",
        "semester",
        "ue",
        "ec",
        "ec__ue",
        "ec__ue__semester",
        "ec__ue__semester__academic_class",
    )
    if branch is not None:
        queryset = queryset.filter(branch=branch)
    if teacher is not None:
        queryset = queryset.filter(teacher=teacher)
    if academic_class is not None:
        queryset = queryset.filter(
            Q(academic_class=academic_class)
            | Q(semester__academic_class=academic_class)
            | Q(ue__semester__academic_class=academic_class)
            | Q(ec__ue__semester__academic_class=academic_class)
        )
    if semester is not None:
        queryset = queryset.filter(
            Q(semester=semester)
            | Q(academic_class=semester.academic_class)
            | Q(ue__semester=semester)
            | Q(ec__ue__semester=semester)
        )
    if ue is not None:
        queryset = queryset.filter(Q(ue=ue) | Q(semester=ue.semester) | Q(academic_class=ue.semester.academic_class))
    if ec is not None:
        queryset = queryset.filter(Q(ec=ec) | Q(ue=ec.ue) | Q(semester=ec.ue.semester) | Q(academic_class=ec.ue.semester.academic_class))
    if active_only:
        queryset = queryset.filter(is_active=True, status=DirectorTeacherAssignment.STATUS_ACTIVE)
    return queryset


def _assignment_targets(assignment):
    if assignment.ec_id:
        return [assignment.ec.ue.semester.academic_class_id]
    if assignment.ue_id:
        return [assignment.ue.semester.academic_class_id]
    if assignment.semester_id:
        return [assignment.semester.academic_class_id]
    if assignment.academic_class_id:
        return [assignment.academic_class_id]
    return []


def _assignment_covers_ec(assignment, ec):
    if assignment.ec_id:
        return assignment.ec_id == ec.id
    if assignment.ue_id:
        return assignment.ue_id == ec.ue_id
    if assignment.semester_id:
        return assignment.semester_id == ec.ue.semester_id
    if assignment.academic_class_id:
        return assignment.academic_class_id == ec.ue.semester.academic_class_id
    return False


def get_teacher_assignments_for_class(academic_class):
    return _assignment_queryset(academic_class=academic_class).order_by("teacher__last_name", "teacher__first_name", "id")


def get_teacher_assignments_for_semester(semester):
    return _assignment_queryset(semester=semester).order_by("teacher__last_name", "teacher__first_name", "id")


def get_teacher_assignments_for_teacher(teacher, *, branch=None):
    return _assignment_queryset(teacher=teacher, branch=branch).order_by("starts_on", "ends_on", "id")


def get_teacher_assignment_load(*, branch=None, teacher=None):
    queryset = _assignment_queryset(branch=branch, teacher=teacher)
    return queryset.values("teacher_id").annotate(total_hours=Sum("planned_hours")).order_by("teacher_id")


def get_expired_teacher_assignments(*, branch=None, today: date | None = None):
    today = today or date.today()
    queryset = _assignment_queryset(branch=branch)
    return queryset.filter(ends_on__lt=today)


def get_conflicting_teacher_assignments(*, branch=None, teacher=None, assignment=None):
    queryset = _assignment_queryset(branch=branch, teacher=teacher)
    if assignment is not None and assignment.pk:
        queryset = queryset.exclude(pk=assignment.pk)

    conflicts = []
    for other in queryset:
        if assignment is not None and not _periods_overlap(assignment.starts_on, assignment.ends_on, other.starts_on, other.ends_on):
            continue
        if assignment is not None and assignment.teacher_id == other.teacher_id and _scope_key(assignment) == _scope_key(other):
            conflicts.append(
                {
                    "type": "duplicate_assignment",
                    "message": "Doublon d'affectation pour le meme enseignant et la meme cible.",
                    "assignment": other,
                }
            )
    return conflicts


def get_ecs_without_teacher(*, branch=None, academic_class=None, semester=None):
    queryset = EC.objects.select_related("ue", "ue__semester", "ue__semester__academic_class")
    if branch is not None:
        queryset = queryset.filter(ue__semester__academic_class__branch=branch)
    if academic_class is not None:
        queryset = queryset.filter(ue__semester__academic_class=academic_class)
    if semester is not None:
        queryset = queryset.filter(ue__semester=semester)

    ecs = []
    for ec in queryset:
        assignments = _assignment_queryset(branch=branch, ec=ec)
        if not assignments.exists():
            ecs.append(ec)
    return ecs


def get_teachers_by_class(academic_class):
    assignments = list(get_teacher_assignments_for_class(academic_class))
    teachers = {}
    for assignment in assignments:
        teachers.setdefault(assignment.teacher_id, {
            "teacher": assignment.teacher,
            "assignments": [],
            "classes": set(),
            "semesters": set(),
            "ues": set(),
            "ecs": set(),
            "total_hours": Decimal("0.00"),
        })
        row = teachers[assignment.teacher_id]
        row["assignments"].append(assignment)
        row["total_hours"] += Decimal(str(assignment.planned_hours or 0))
        if assignment.academic_class_id:
            row["classes"].add(assignment.academic_class.display_name)
        if assignment.semester_id:
            row["semesters"].add(f"S{assignment.semester.number}")
        if assignment.ue_id:
            row["ues"].add(assignment.ue.code)
        if assignment.ec_id:
            row["ecs"].add(assignment.ec.title)
    return [
        {
            **row,
            "classes": sorted(row["classes"]),
            "semesters": sorted(row["semesters"]),
            "ues": sorted(row["ues"]),
            "ecs": sorted(row["ecs"]),
        }
        for row in teachers.values()
    ]


def get_teachers_by_semester(semester):
    assignments = list(get_teacher_assignments_for_semester(semester))
    teachers = {}
    for assignment in assignments:
        teachers.setdefault(assignment.teacher_id, {
            "teacher": assignment.teacher,
            "assignments": [],
            "total_hours": Decimal("0.00"),
        })
        teachers[assignment.teacher_id]["assignments"].append(assignment)
        teachers[assignment.teacher_id]["total_hours"] += Decimal(str(assignment.planned_hours or 0))
    return list(teachers.values())


def _scope_key(assignment):
    if assignment.ec_id:
        return ("ec", assignment.ec_id)
    if assignment.ue_id:
        return ("ue", assignment.ue_id)
    if assignment.semester_id:
        return ("semester", assignment.semester_id)
    if assignment.academic_class_id:
        return ("class", assignment.academic_class_id)
    return ("none", assignment.id)


def _periods_overlap(start_a, end_a, start_b, end_b):
    start_a = start_a or date.min
    end_a = end_a or date.max
    start_b = start_b or date.min
    end_b = end_b or date.max
    return start_a <= end_b and end_a >= start_b
