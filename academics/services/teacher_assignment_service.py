from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from academics.permissions.teacher_assignment_permissions import require_teacher_assignment_access
from academics.selectors.teacher_assignment_selectors import get_conflicting_teacher_assignments
from academics.models import AcademicClass, EC, Semester, UE
from portal.models import DirectorTeacherAssignment


@dataclass
class TeacherAssignmentResult:
    assignment: DirectorTeacherAssignment
    created: bool


def _parse_date(raw_value, field_name):
    value = (raw_value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError({field_name: "Date invalide."}) from exc


def _parse_planned_hours(raw_value):
    if raw_value is None:
        return None
    if isinstance(raw_value, Decimal):
        planned_hours = raw_value
    else:
        value = str(raw_value).strip()
        if value == "":
            return None
        normalized = value.replace(",", ".")
        try:
            planned_hours = Decimal(normalized)
        except InvalidOperation as exc:
            raise ValidationError({"planned_hours": "Le volume horaire est invalide."}) from exc
    try:
        planned_hours = Decimal(str(planned_hours))
    except InvalidOperation as exc:
        raise ValidationError({"planned_hours": "Le volume horaire est invalide."}) from exc
    if planned_hours <= 0:
        raise ValidationError({"planned_hours": "Le volume horaire doit etre superieur a 0."})
    return planned_hours


def _teacher_is_active(teacher):
    profile = getattr(teacher, "profile", None)
    if not getattr(teacher, "is_active", False):
        return False
    if profile is None:
        return False
    return getattr(profile, "employment_status", "active") == "active"


def _get_branch_from_target(*, academic_class=None, semester=None, ue=None, ec=None):
    if academic_class is not None:
        return academic_class.branch
    if semester is not None:
        return semester.academic_class.branch
    if ue is not None:
        return ue.semester.academic_class.branch
    if ec is not None:
        return ec.ue.semester.academic_class.branch
    return None


def _resolve_target(*, branch, academic_class=None, semester=None, ue=None, ec=None):
    if ec is not None:
        academic_class = ec.ue.semester.academic_class
        semester = ec.ue.semester
        ue = ec.ue
        scope_type = "ec"
    elif ue is not None:
        academic_class = ue.semester.academic_class
        semester = ue.semester
        scope_type = "ue"
    elif semester is not None:
        academic_class = semester.academic_class
        scope_type = "semester"
    elif academic_class is not None:
        scope_type = "class"
    else:
        raise ValidationError("Une cible pedagogique est requise.")

    target_branch = _get_branch_from_target(academic_class=academic_class, semester=semester, ue=ue, ec=ec)
    if target_branch is None:
        raise ValidationError("Cible pedagogique invalide.")
    if branch is not None and target_branch.pk != branch.pk:
        raise ValidationError("La cible selectionnee est hors annexe.")
    return {
        "scope_type": scope_type,
        "academic_class": academic_class,
        "semester": semester,
        "ue": ue,
        "ec": ec,
        "branch": target_branch,
    }


def _assignment_lookup_kwargs(*, teacher, academic_class, semester, ue, ec, starts_on, ends_on, scope_type):
    return {
        "teacher": teacher,
        "academic_class": academic_class,
        "semester": semester,
        "ue": ue,
        "ec": ec,
        "starts_on": starts_on,
        "ends_on": ends_on,
        "scope_type": scope_type,
    }


def _apply_target_fields(assignment, target):
    assignment.scope_type = target["scope_type"]
    assignment.academic_class = target["academic_class"]
    assignment.semester = target["semester"]
    assignment.ue = target["ue"]
    assignment.ec = target["ec"]
    assignment.branch = target["branch"]


def _validate_access(actor, branch):
    if actor is not None:
        require_teacher_assignment_access(actor, branch)


def _validate_target_combo(*, target, teacher):
    if not _teacher_is_active(teacher):
        raise ValidationError("L'enseignant doit etre actif pour recevoir une affectation.")
    if target["scope_type"] == "class" and target["academic_class"] is None:
        raise ValidationError("La classe est obligatoire.")
    if target["scope_type"] == "semester" and target["semester"] is None:
        raise ValidationError("Le semestre est obligatoire.")
    if target["scope_type"] == "ue" and target["ue"] is None:
        raise ValidationError("L'UE est obligatoire.")
    if target["scope_type"] == "ec" and target["ec"] is None:
        raise ValidationError("L'EC est obligatoire.")


def _validate_explicit_target_alignment(*, academic_class=None, semester=None, ue=None, ec=None):
    if ec is not None:
        ec_class = ec.ue.semester.academic_class
        if academic_class is not None and academic_class.pk != ec_class.pk:
            raise ValidationError("La matiere selectionnee ne correspond pas a la classe choisie.")
        if semester is not None and semester.pk != ec.ue.semester.pk:
            raise ValidationError("La matiere selectionnee ne correspond pas au semestre choisi.")
        if ue is not None and ue.pk != ec.ue.pk:
            raise ValidationError("La matiere selectionnee ne correspond pas a l'UE choisie.")
    if ue is not None:
        ue_class = ue.semester.academic_class
        if academic_class is not None and academic_class.pk != ue_class.pk:
            raise ValidationError("L'UE selectionnee ne correspond pas a la classe choisie.")
        if semester is not None and semester.pk != ue.semester.pk:
            raise ValidationError("L'UE selectionnee ne correspond pas au semestre choisi.")
    if semester is not None and academic_class is not None and semester.academic_class_id != academic_class.pk:
        raise ValidationError("Le semestre selectionne ne correspond pas a la classe choisie.")


def _validate_conflicts(*, assignment, branch, teacher):
    conflicts = get_conflicting_teacher_assignments(branch=branch, teacher=teacher, assignment=assignment)
    if conflicts:
        messages = []
        for item in conflicts:
            message = item.get("message")
            if message and message not in messages:
                messages.append(message)
        raise ValidationError(messages)


def _normalize_assignment_inputs(*, branch, academic_class=None, semester=None, ue=None, ec=None):
    target = _resolve_target(branch=branch, academic_class=academic_class, semester=semester, ue=ue, ec=ec)
    return target


@transaction.atomic
def create_teacher_assignment(
    *,
    actor,
    teacher,
    branch,
    academic_class=None,
    semester=None,
    ue=None,
    ec=None,
    room_label="",
    planned_hours=None,
    starts_on=None,
    ends_on=None,
    status=None,
    created_by=None,
):
    _validate_access(actor, branch)
    _validate_explicit_target_alignment(academic_class=academic_class, semester=semester, ue=ue, ec=ec)
    target = _normalize_assignment_inputs(branch=branch, academic_class=academic_class, semester=semester, ue=ue, ec=ec)
    _validate_target_combo(target=target, teacher=teacher)

    room_label = (room_label or "").strip()
    if target["scope_type"] in {"class", "semester", "ue", "ec"} and not room_label:
        raise ValidationError("La salle de reference est obligatoire pour une affectation.")
    planned_hours_value = _parse_planned_hours(planned_hours)
    if planned_hours_value is None:
        raise ValidationError("Le volume horaire est obligatoire pour une affectation.")

    starts_on_value = _parse_date(starts_on, "starts_on")
    ends_on_value = _parse_date(ends_on, "ends_on")
    assignment = DirectorTeacherAssignment(
        teacher=teacher,
        room_label=room_label,
        planned_hours=planned_hours_value,
        starts_on=starts_on_value,
        ends_on=ends_on_value,
        status=status or DirectorTeacherAssignment.STATUS_ACTIVE,
        created_by=created_by or actor,
        updated_by=actor,
    )
    _apply_target_fields(assignment, target)
    assignment.full_clean()
    _validate_conflicts(assignment=assignment, branch=assignment.branch, teacher=teacher)
    assignment.save()
    return TeacherAssignmentResult(assignment=assignment, created=True)


@transaction.atomic
def update_teacher_assignment(
    *,
    actor,
    assignment,
    branch,
    teacher=None,
    academic_class=None,
    semester=None,
    ue=None,
    ec=None,
    room_label=None,
    planned_hours=None,
    starts_on=None,
    ends_on=None,
    status=None,
):
    _validate_access(actor, branch)
    if branch is not None and assignment.branch_id != branch.pk:
        raise ValidationError("Affectation hors annexe.")
    _validate_explicit_target_alignment(
        academic_class=academic_class or assignment.academic_class,
        semester=semester or assignment.semester,
        ue=ue or assignment.ue,
        ec=ec or assignment.ec,
    )
    target = _normalize_assignment_inputs(
        branch=branch,
        academic_class=academic_class or assignment.academic_class,
        semester=semester or assignment.semester,
        ue=ue or assignment.ue,
        ec=ec or assignment.ec,
    )
    _validate_target_combo(target=target, teacher=teacher or assignment.teacher)

    if teacher is not None:
        if not _teacher_is_active(teacher):
            raise ValidationError("L'enseignant doit etre actif pour recevoir une affectation.")
        assignment.teacher = teacher
    if room_label is not None:
        assignment.room_label = (room_label or "").strip()
    if planned_hours is not None:
        assignment.planned_hours = _parse_planned_hours(planned_hours)
    if starts_on is not None:
        assignment.starts_on = _parse_date(starts_on, "starts_on")
    if ends_on is not None:
        assignment.ends_on = _parse_date(ends_on, "ends_on")
    if status is not None:
        assignment.status = status

    _apply_target_fields(assignment, target)
    assignment.updated_by = actor
    assignment.full_clean()
    _validate_conflicts(assignment=assignment, branch=assignment.branch, teacher=assignment.teacher)
    assignment.save()
    return TeacherAssignmentResult(assignment=assignment, created=False)


@transaction.atomic
def activate_teacher_assignment(*, actor, assignment, branch):
    _validate_access(actor, branch)
    assignment.status = DirectorTeacherAssignment.STATUS_ACTIVE
    assignment.is_active = True
    assignment.suspended_at = None
    assignment.updated_by = actor
    assignment.full_clean()
    assignment.save(update_fields=["status", "is_active", "suspended_at", "archived_at", "updated_by", "updated_at"])
    return assignment


@transaction.atomic
def suspend_teacher_assignment(*, actor, assignment, branch):
    _validate_access(actor, branch)
    assignment.status = DirectorTeacherAssignment.STATUS_SUSPENDED
    assignment.is_active = False
    assignment.suspended_at = timezone.now()
    assignment.updated_by = actor
    assignment.full_clean()
    assignment.save(update_fields=["status", "is_active", "suspended_at", "archived_at", "updated_by", "updated_at"])
    return assignment


@transaction.atomic
def archive_teacher_assignment(*, actor, assignment, branch):
    _validate_access(actor, branch)
    assignment.status = DirectorTeacherAssignment.STATUS_ARCHIVED
    assignment.is_active = False
    assignment.archived_at = timezone.now()
    assignment.updated_by = actor
    assignment.full_clean()
    assignment.save(update_fields=["status", "is_active", "archived_at", "updated_by", "updated_at"])
    return assignment


def delete_teacher_assignment(*, actor, assignment, branch):
    return archive_teacher_assignment(actor=actor, assignment=assignment, branch=branch)
