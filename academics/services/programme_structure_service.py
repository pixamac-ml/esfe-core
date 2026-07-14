from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from academics.models import EC, Semester, UE
from academics.permissions.programme_structure_permissions import require_programme_structure_access


MAX_UE_CREDITS = Decimal("6.00")


def _parse_positive_decimal(value, field_label):
    try:
        parsed = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, TypeError, AttributeError):
        raise ValidationError(f"{field_label} invalide.")
    if parsed <= 0:
        raise ValidationError(f"{field_label} doit etre superieur a 0.")
    return parsed


def _semester_branch(semester):
    return semester.academic_class.branch


def _ue_branch(ue):
    return ue.semester.academic_class.branch


def _ec_branch(ec):
    return ec.ue.semester.academic_class.branch


def _require_actor_access(actor, branch):
    if actor is not None:
        require_programme_structure_access(actor, branch)


def _get_semester_for_branch(*, semester_id, branch):
    if not str(semester_id or "").strip().isdigit():
        raise ValidationError("Semestre obligatoire.")
    semester = (
        Semester.objects.select_related("academic_class", "academic_class__branch")
        .filter(pk=semester_id, academic_class__branch=branch)
        .first()
    )
    if semester is None:
        raise ValidationError("Semestre invalide pour cette annexe.")
    return semester


def _get_ue_for_branch(*, ue_id, branch):
    if not str(ue_id or "").strip().isdigit():
        raise ValidationError("UE obligatoire.")
    ue = (
        UE.objects.select_related("semester", "semester__academic_class", "semester__academic_class__branch")
        .filter(pk=ue_id, semester__academic_class__branch=branch)
        .first()
    )
    if ue is None:
        raise ValidationError("UE introuvable pour cette annexe.")
    return ue


def _get_ec_for_branch(*, ec_id, branch):
    if not str(ec_id or "").strip().isdigit():
        raise ValidationError("EC obligatoire.")
    ec = (
        EC.objects.select_related("ue", "ue__semester", "ue__semester__academic_class", "ue__semester__academic_class__branch")
        .filter(pk=ec_id, ue__semester__academic_class__branch=branch)
        .first()
    )
    if ec is None:
        raise ValidationError("EC introuvable pour cette annexe.")
    return ec


def _ec_credit_sum(queryset):
    return queryset.aggregate(total=Sum("credit_required"))["total"] or Decimal("0.00")


def _validate_ec_credit_balance(*, ue, credit_required, ec=None):
    active_ecs = EC.objects.filter(ue=ue).exclude(structure_status=EC.STRUCTURE_ARCHIVED)
    if ec and ec.pk:
        active_ecs = active_ecs.exclude(pk=ec.pk)

    ue_total = _ec_credit_sum(active_ecs) + credit_required
    if ue_total > MAX_UE_CREDITS:
        raise ValidationError("Une UE ne peut pas depasser 6 credits.")

    semester = ue.semester
    semester_ecs = EC.objects.filter(ue__semester=semester).exclude(structure_status=EC.STRUCTURE_ARCHIVED)
    if ec and ec.pk:
        semester_ecs = semester_ecs.exclude(pk=ec.pk)
    semester_total = _ec_credit_sum(semester_ecs) + credit_required
    if semester.total_required_credits and semester_total > semester.total_required_credits:
        raise ValidationError("Le total des credits du semestre depasse les credits requis.")


def _refresh_ue_status(ue):
    if ue.structure_status in {UE.STRUCTURE_VALIDATED, UE.STRUCTURE_PUBLISHED, UE.STRUCTURE_ARCHIVED}:
        return ue
    has_active_ec = ue.ecs.exclude(structure_status=EC.STRUCTURE_ARCHIVED).exists()
    ue.structure_status = UE.STRUCTURE_COMPLETE if has_active_ec else UE.STRUCTURE_DRAFT
    ue.save(update_fields=["structure_status", "archived_at"])
    return ue


def ec_has_blocking_usage(ec):
    if ec.grades.exists():
        return True
    if ec.schedule_events.exists():
        return True
    if ec.weekly_schedule_slots.exists():
        return True
    if ec.lesson_logs.exists():
        return True
    if ec.chapters.exists():
        return True
    if ec.academic_cycle_debts.exists():
        return True
    if ec.director_teacher_assignments.exists():
        return True
    if ec.ue.semester.bulletins.exists():
        return True
    return False


def ue_has_blocking_usage(ue):
    if ue.academic_cycle_debts.exists():
        return True
    if ue.semester.bulletins.exists():
        return True
    return any(ec_has_blocking_usage(ec) for ec in ue.ecs.all())


@transaction.atomic
def create_ue(*, actor, semester, code, title):
    branch = _semester_branch(semester)
    _require_actor_access(actor, branch)

    code = (code or "").strip().upper()
    title = (title or "").strip()
    if not code or not title:
        raise ValidationError("Code UE et intitule obligatoires.")
    if UE.objects.filter(semester=semester, code=code).exists():
        raise ValidationError("Une UE existe deja avec ce code dans ce semestre.")

    ue = UE(semester=semester, code=code, title=title, structure_status=UE.STRUCTURE_DRAFT)
    ue.full_clean()
    ue.save()
    return ue


@transaction.atomic
def update_ue(*, actor, ue, semester=None, code=None, title=None, structure_status=None):
    branch = _ue_branch(ue)
    _require_actor_access(actor, branch)

    if semester is not None:
        if _semester_branch(semester).pk != branch.pk:
            raise ValidationError("Le semestre cible n'appartient pas a la meme annexe.")
        ue.semester = semester
    if code is not None:
        ue.code = (code or "").strip().upper()
    if title is not None:
        ue.title = (title or "").strip()
    if structure_status is not None:
        if structure_status not in dict(UE.STRUCTURE_STATUS_CHOICES):
            raise ValidationError("Statut UE invalide.")
        ue.structure_status = structure_status
        ue.archived_at = timezone.now() if structure_status == UE.STRUCTURE_ARCHIVED else None
    if not ue.code or not ue.title:
        raise ValidationError("Code UE et intitule obligatoires.")
    duplicate = UE.objects.filter(semester=ue.semester, code=ue.code).exclude(pk=ue.pk)
    if duplicate.exists():
        raise ValidationError("Une UE existe deja avec ce code dans ce semestre.")

    ue.full_clean()
    ue.save()
    return ue


@transaction.atomic
def create_ec(*, actor, ue, title, credit_required, coefficient):
    branch = _ue_branch(ue)
    _require_actor_access(actor, branch)

    title = (title or "").strip()
    if not title:
        raise ValidationError("Intitule EC obligatoire.")
    credit_value = _parse_positive_decimal(credit_required, "Credit EC")
    coefficient_value = _parse_positive_decimal(coefficient, "Coefficient EC")
    _validate_ec_credit_balance(ue=ue, credit_required=credit_value)

    ec = EC(
        ue=ue,
        title=title,
        credit_required=credit_value,
        coefficient=coefficient_value,
        structure_status=EC.STRUCTURE_COMPLETE,
    )
    ec.full_clean()
    ec.save()
    _refresh_ue_status(ue)
    return ec


@transaction.atomic
def update_ec(*, actor, ec, ue=None, title=None, credit_required=None, coefficient=None, structure_status=None):
    branch = _ec_branch(ec)
    _require_actor_access(actor, branch)

    target_ue = ue or ec.ue
    if _ue_branch(target_ue).pk != branch.pk:
        raise ValidationError("L'UE cible n'appartient pas a la meme annexe.")
    if target_ue.semester.academic_class_id != ec.ue.semester.academic_class_id:
        raise ValidationError("Impossible de rattacher un EC a une UE d'une autre classe.")

    if title is not None:
        ec.title = (title or "").strip()
    if not ec.title:
        raise ValidationError("Intitule EC obligatoire.")
    credit_value = ec.credit_required if credit_required is None else _parse_positive_decimal(credit_required, "Credit EC")
    coefficient_value = ec.coefficient if coefficient is None else _parse_positive_decimal(coefficient, "Coefficient EC")
    _validate_ec_credit_balance(ue=target_ue, credit_required=credit_value, ec=ec)

    ec.ue = target_ue
    ec.credit_required = credit_value
    ec.coefficient = coefficient_value
    if structure_status is not None:
        if structure_status not in dict(EC.STRUCTURE_STATUS_CHOICES):
            raise ValidationError("Statut EC invalide.")
        ec.structure_status = structure_status
        ec.archived_at = timezone.now() if structure_status == EC.STRUCTURE_ARCHIVED else None
    ec.full_clean()
    ec.save()
    _refresh_ue_status(target_ue)
    return ec


@transaction.atomic
def archive_ec(*, actor, ec):
    branch = _ec_branch(ec)
    _require_actor_access(actor, branch)
    if ec_has_blocking_usage(ec):
        raise ValidationError("Suppression impossible: cet EC est deja utilise dans le systeme.")
    ec.structure_status = EC.STRUCTURE_ARCHIVED
    ec.archived_at = timezone.now()
    ec.full_clean()
    ec.save(update_fields=["structure_status", "archived_at"])
    _refresh_ue_status(ec.ue)
    return ec


@transaction.atomic
def archive_ue(*, actor, ue):
    branch = _ue_branch(ue)
    _require_actor_access(actor, branch)
    if ue_has_blocking_usage(ue):
        raise ValidationError("Suppression impossible: cette UE est deja utilisee dans le systeme.")
    ue.structure_status = UE.STRUCTURE_ARCHIVED
    ue.archived_at = timezone.now()
    ue.full_clean()
    ue.save(update_fields=["structure_status", "archived_at"])
    return ue


def save_ue_for_branch(*, branch, actor=None, ue_id=None, semester_id=None, code="", title=""):
    semester = _get_semester_for_branch(semester_id=semester_id, branch=branch)
    if ue_id:
        ue = _get_ue_for_branch(ue_id=ue_id, branch=branch)
        return update_ue(actor=actor, ue=ue, semester=semester, code=code, title=title)
    return create_ue(actor=actor, semester=semester, code=code, title=title)


def save_ec_for_branch(*, branch, actor=None, ec_id=None, ue_id=None, title="", coefficient="", credit_required=""):
    ue = _get_ue_for_branch(ue_id=ue_id, branch=branch)
    if ec_id:
        ec = _get_ec_for_branch(ec_id=ec_id, branch=branch)
        return update_ec(
            actor=actor,
            ec=ec,
            ue=ue,
            title=title,
            coefficient=coefficient,
            credit_required=credit_required,
        )
    return create_ec(actor=actor, ue=ue, title=title, coefficient=coefficient, credit_required=credit_required)


def archive_ec_for_branch(*, branch, actor=None, ec_id):
    ec = _get_ec_for_branch(ec_id=ec_id, branch=branch)
    return archive_ec(actor=actor, ec=ec)
