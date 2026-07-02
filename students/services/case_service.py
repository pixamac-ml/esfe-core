"""Gestion unifiee des cas de suivi surveillant general (etudiants + enseignants)."""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.utils import timezone

from branches.models import Branch
from students.models import StudentCase, StudentCaseNote, TeacherCase, TeacherCaseNote
from notifier.models import NotificationMessage
from notifier.services import NotificationBus

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


def escalate_case_to_director(*, case, user):
    """Transmit a branch-scoped disciplinary case to the Direction des études."""
    if case.branch_id is None:
        raise ValidationError("Le cas doit être rattaché à une annexe.")

    if isinstance(case, StudentCase):
        case.status = StudentCase.STATUS_ESCALADE
        case.save(update_fields=["status", "updated_at"])
        note_model = StudentCaseNote
        subject_name = case.student.full_name
        case_kind = "Étudiant"
    elif isinstance(case, TeacherCase):
        note_model = TeacherCaseNote
        subject_name = case.teacher.get_full_name() or case.teacher.username
        case_kind = "Enseignant"
    else:
        raise ValidationError("Type de cas non pris en charge.")

    note_model.objects.create(
        case=case,
        author=user,
        content="Cas transmis à la Direction des études.",
    )

    directors = get_user_model().objects.filter(
        is_active=True,
        profile__branch_id=case.branch_id,
        profile__position="director_of_studies",
    )
    for director in directors:
        NotificationBus.notify(
            recipient=director,
            actor=user,
            event_type="disciplinary_case_escalated",
            title="Cas disciplinaire transmis",
            body=f"{case_kind} : {subject_name} — {case.title}",
            source_app="students",
            channels=(
                NotificationMessage.CHANNEL_IN_APP,
                NotificationMessage.CHANNEL_WEBSOCKET,
            ),
            priority=NotificationMessage.PRIORITY_HIGH,
            metadata={
                "branch_id": case.branch_id,
                "case_id": case.pk,
                "case_kind": "student" if isinstance(case, StudentCase) else "teacher",
                "url": "/portal/dashboard/?section=home",
            },
        )
    return case
