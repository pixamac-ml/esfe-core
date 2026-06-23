"""Gestion unifiee des cas de suivi surveillant general (etudiants + enseignants)."""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.utils import timezone

from branches.models import Branch
from students.models import StudentCase, StudentCaseNote, TeacherCase, TeacherCaseNote

_PRIORITY_ORDER = {
    StudentCase.PRIORITY_CRITIQUE: 0,
    StudentCase.PRIORITY_URGENTE: 1,
    StudentCase.PRIORITY_NORMALE: 2,
    StudentCase.PRIORITY_FAIBLE: 3,
}


def _normalize_branch(branch: Branch | int | None) -> Branch:
    if branch is None:
        raise ValidationError("Une annexe est obligatoire.")
    if isinstance(branch, Branch):
        return branch
    return Branch.objects.get(pk=branch)


def list_open_cases(*, branch, limit: int = 100):
    """Fusionne cas etudiants et enseignants ouverts, tries priorite puis recence."""
    branch = _normalize_branch(branch)
    student_cases = list(
        StudentCase.objects.select_related("student__inscription__candidature", "opened_by")
        .filter(branch=branch)
        .exclude(status=StudentCase.STATUS_RESOLU)[:limit]
    )
    teacher_cases = list(
        TeacherCase.objects.select_related("teacher", "opened_by")
        .filter(branch=branch)
        .exclude(status=TeacherCase.STATUS_RESOLU)[:limit]
    )
    combined = [("student", c) for c in student_cases] + [("teacher", c) for c in teacher_cases]
    combined.sort(key=lambda pair: (_PRIORITY_ORDER.get(pair[1].priority, 9), -pair[1].pk))
    return combined[:limit]


def count_open_cases(*, branch) -> int:
    branch = _normalize_branch(branch)
    return (
        StudentCase.objects.filter(branch=branch).exclude(status=StudentCase.STATUS_RESOLU).count()
        + TeacherCase.objects.filter(branch=branch).exclude(status=TeacherCase.STATUS_RESOLU).count()
    )


def advance_student_case(*, case: StudentCase, user):
    flow = StudentCase.SIMPLE_FLOW_STATUSES
    if case.status not in flow:
        raise ValidationError(
            "Ce cas n'est pas dans le flux standard (nouveau / en cours / convoque / resolu)."
        )
    idx = flow.index(case.status)
    if idx >= len(flow) - 1:
        return case
    case.status = flow[idx + 1]
    if case.status == StudentCase.STATUS_RESOLU:
        case.resolved_at = timezone.now()
        case.save(update_fields=["status", "resolved_at", "updated_at"])
    else:
        case.save(update_fields=["status", "updated_at"])
    StudentCaseNote.objects.create(
        case=case, author=user, content=f"Cas passe a : {case.get_status_display()}."
    )
    return case


def advance_teacher_case(*, case: TeacherCase, user):
    statuses = [value for value, _ in TeacherCase.STATUS_CHOICES]
    idx = statuses.index(case.status)
    if idx >= len(statuses) - 1:
        return case
    case.status = statuses[idx + 1]
    if case.status == TeacherCase.STATUS_RESOLU:
        case.resolved_at = timezone.now()
        case.save(update_fields=["status", "resolved_at", "updated_at"])
    else:
        case.save(update_fields=["status", "updated_at"])
    TeacherCaseNote.objects.create(
        case=case, author=user, content=f"Cas passe a : {case.get_status_display()}."
    )
    return case


def create_teacher_case(
    *,
    teacher,
    branch,
    case_type,
    title,
    opened_by,
    description: str = "",
    priority: str = TeacherCase.PRIORITY_NORMALE,
):
    branch = _normalize_branch(branch)
    return TeacherCase.objects.create(
        teacher=teacher,
        branch=branch,
        case_type=case_type,
        title=title,
        description=description,
        priority=priority,
        opened_by=opened_by,
    )
