from datetime import datetime

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.db import transaction
from django.utils import timezone

from academics.models import (
    AcademicCalendar,
    AcademicCalendarAdjustment,
    AcademicCalendarDisruption,
    AcademicCalendarEntry,
)
from academics.permissions.calendar_permissions import (
    require_calendar_access,
    require_calendar_branch_access,
)


CALENDAR_MUTABLE_FIELDS = {
    "official_title",
    "administrative_reference",
    "general_observations",
}
ENTRY_MUTABLE_FIELDS = {
    "title",
    "description",
    "event_type",
    "start_datetime",
    "end_datetime",
    "all_day",
    "target_scope",
    "programme",
    "academic_class",
    "semester",
    "color",
    "icon",
    "is_blocking",
    "status",
}


def _academic_year_dependencies(academic_year):
    """Liste les objets lies a une annee ; une suppression doit etre sans effet de bord."""
    from django.core.exceptions import ObjectDoesNotExist

    dependencies = []
    for relation in academic_year._meta.related_objects:
        accessor = relation.get_accessor_name()
        if not accessor or accessor.endswith("+"):
            continue
        try:
            related = getattr(academic_year, accessor)
            exists = related.exists() if hasattr(related, "exists") else related is not None
        except ObjectDoesNotExist:
            exists = False
        if exists:
            dependencies.append(relation.related_model._meta.verbose_name_plural)
    return dependencies


@transaction.atomic
def delete_academic_year(*, academic_year, actor, confirmation, branch=None):
    """Purge une annee inactive et ses calendriers de preparation, sans toucher a l'active."""
    from accounts.access import get_user_role
    from academic_cycle.services.audit_service import log_action

    confirmation = (confirmation or "").strip()
    if confirmation != academic_year.name:
        raise ValidationError(
            f"Pour confirmer la suppression, saisissez exactement : {academic_year.name}."
        )

    is_dg = get_user_role(actor) == "directeur_general"
    if academic_year.is_active and not is_dg:
        raise ValidationError(
            "L'annee academique active est protegee. Seul le Directeur General peut "
            "autoriser sa suppression."
        )

    # Une annee inactive peut etre abandonnee avec ses calendriers de travail.
    # Les avenants et perturbations protegent le calendrier : on les retire
    # explicitement avant les entrees et le calendrier lui-meme.
    calendars = academic_year.calendars.all()
    if branch is not None:
        calendars = calendars.filter(branch=branch)
    calendars = list(calendars)
    if not academic_year.is_active or is_dg:
        for calendar in calendars:
            calendar.adjustments.all().delete()
            calendar.disruptions.all().delete()
            calendar.entries.all().delete()
        if calendars:
            calendar_ids = [calendar.id for calendar in calendars]
            AcademicCalendar.objects.filter(revision_of_id__in=calendar_ids).update(
                revision_of=None
            )
            AcademicCalendar.objects.filter(id__in=calendar_ids).delete()

    dependencies = _academic_year_dependencies(academic_year)
    if dependencies:
        readable = ", ".join(sorted(set(dependencies))[:5])
        raise ValidationError(
            "Cette annee contient encore des donnees academiques qui ne peuvent pas "
            f"etre effacees automatiquement : {readable}."
        )

    old_values = {
        "name": academic_year.name,
        "start_date": academic_year.start_date.isoformat(),
        "end_date": academic_year.end_date.isoformat(),
        "is_active": academic_year.is_active,
    }
    log_action(
        actor,
        "academic_year.deleted",
        academic_year,
        old_values=old_values,
        reason="Suppression confirmee de l'annee et de ses calendriers de preparation.",
    )
    academic_year.delete()


def _apply_changes(instance, changes, allowed_fields):
    unknown = set(changes) - allowed_fields
    if unknown:
        raise ValidationError(f"Champs non modifiables : {', '.join(sorted(unknown))}.")
    for field, value in changes.items():
        setattr(instance, field, value)


def _calendar_is_editable(calendar):
    return calendar.status in {
        AcademicCalendar.STATUS_DRAFT,
        AcademicCalendar.STATUS_REJECTED,
    }


def _validate_calendar_for_submission(calendar):
    if not calendar.entries.exists():
        raise ValidationError("Un calendrier vide ne peut pas etre soumis.")
    for entry in calendar.entries.all():
        entry.full_clean()
    _validate_no_entry_overlap(calendar)
    errors = [
        item["message"]
        for item in get_calendar_readiness(calendar)
        if item["level"] == "error"
    ]
    if errors:
        raise ValidationError(errors)


@transaction.atomic
def create_calendar(*, actor, branch, academic_year, version=1):
    require_calendar_branch_access(actor, branch)
    calendar = AcademicCalendar(
        branch=branch,
        academic_year=academic_year,
        version=version,
        status=AcademicCalendar.STATUS_DRAFT,
        created_by=actor,
        updated_by=actor,
    )
    calendar.full_clean()
    calendar.save()
    return calendar


@transaction.atomic
def update_calendar(calendar, *, actor, **changes):
    require_calendar_access(actor, calendar)
    if not _calendar_is_editable(calendar):
        raise ValidationError("Seul un calendrier brouillon ou retourne peut etre modifie.")
    _apply_changes(calendar, changes, CALENDAR_MUTABLE_FIELDS)
    calendar.updated_by = actor
    calendar.full_clean()
    calendar.save()
    return calendar


@transaction.atomic
def submit_calendar(calendar, *, actor):
    require_calendar_access(actor, calendar)
    if not _calendar_is_editable(calendar):
        raise ValidationError("Seul un calendrier brouillon ou retourne peut etre soumis.")
    _validate_calendar_for_submission(calendar)
    calendar.status = AcademicCalendar.STATUS_SUBMITTED
    calendar.submitted_by = actor
    calendar.submitted_at = timezone.now()
    calendar.rejected_by = None
    calendar.rejected_at = None
    calendar.rejection_reason = ""
    calendar.updated_by = actor
    calendar.save()
    return calendar


@transaction.atomic
def validate_calendar(calendar, *, actor):
    """Valide une soumission ; conserve le flux direct minimal des anciennes API."""
    require_calendar_access(actor, calendar)
    if calendar.status == AcademicCalendar.STATUS_DRAFT:
        # Compatibilite : les integrations historiques valident directement un
        # brouillon. Le nouveau parcours DE passe obligatoirement par submit.
        if not calendar.entries.exists():
            raise ValidationError("Un calendrier vide ne peut pas etre valide.")
        for entry in calendar.entries.all():
            entry.full_clean()
        _validate_no_entry_overlap(calendar)
    elif calendar.status == AcademicCalendar.STATUS_SUBMITTED:
        _validate_calendar_for_submission(calendar)
    else:
        raise ValidationError("Seul un calendrier soumis peut etre valide.")
    calendar.status = AcademicCalendar.STATUS_VALIDATED
    calendar.validated_by = actor
    calendar.validated_at = timezone.now()
    calendar.updated_by = actor
    calendar.save()
    return calendar


@transaction.atomic
def reject_calendar(calendar, *, actor, reason):
    require_calendar_access(actor, calendar)
    reason = (reason or "").strip()
    if calendar.status not in {
        AcademicCalendar.STATUS_SUBMITTED,
        AcademicCalendar.STATUS_VALIDATED,
    }:
        raise ValidationError("Seul un calendrier soumis ou valide peut etre retourne.")
    if not reason:
        raise ValidationError("Le motif de retour est obligatoire.")
    calendar.status = AcademicCalendar.STATUS_REJECTED
    calendar.rejected_by = actor
    calendar.rejected_at = timezone.now()
    calendar.rejection_reason = reason
    calendar.updated_by = actor
    calendar.save()
    return calendar


def _target_scope_overlaps(left, right):
    """Indique si deux cibles académiques couvrent au moins le même public."""
    if (
        left.target_scope == AcademicCalendarEntry.SCOPE_BRANCH
        or right.target_scope == AcademicCalendarEntry.SCOPE_BRANCH
    ):
        return True

    def _programme_id(item):
        if getattr(item, "programme_id", None):
            return item.programme_id
        academic_class = getattr(item, "academic_class", None)
        if academic_class is not None:
            return academic_class.programme_id
        semester = getattr(item, "semester", None)
        return semester.academic_class.programme_id if semester is not None else None

    def _class_id(item):
        if getattr(item, "academic_class_id", None):
            return item.academic_class_id
        semester = getattr(item, "semester", None)
        return semester.academic_class_id if semester is not None else None

    left_semester_id = getattr(left, "semester_id", None)
    right_semester_id = getattr(right, "semester_id", None)
    if left_semester_id and right_semester_id:
        return left_semester_id == right_semester_id

    left_class_id = _class_id(left)
    right_class_id = _class_id(right)
    if left_class_id and right_class_id:
        return left_class_id == right_class_id

    left_programme_id = _programme_id(left)
    right_programme_id = _programme_id(right)
    if left_programme_id and right_programme_id:
        return left_programme_id == right_programme_id
    return False


def _validate_no_entry_overlap(calendar):
    """Verifie les chevauchements des periodes bloquantes sur la meme audience."""
    entries = list(
        calendar.entries
        .filter(is_blocking=True)
        .exclude(status=AcademicCalendarEntry.STATUS_CANCELLED)
        .select_related("programme", "academic_class", "semester", "semester__academic_class")
    )
    for index, entry in enumerate(entries):
        for other in entries[index + 1:]:
            if entry.start_datetime >= other.end_datetime or entry.end_datetime <= other.start_datetime:
                continue
            if not _target_scope_overlaps(entry, other):
                continue
            raise ValidationError(
                f"Les periodes bloquantes '{entry.title}' et '{other.title}' "
                f"se chevauchent pour une meme audience."
            )


def get_calendar_readiness(calendar):
    """Retourne les controles lisibles avant soumission, sans modifier les donnees."""
    entries = list(calendar.entries.exclude(status=AcademicCalendarEntry.STATUS_CANCELLED))
    event_types = {entry.event_type for entry in entries}
    checks = []

    def add(level, code, message):
        checks.append({"level": level, "code": code, "message": message})

    if not entries:
        add("error", "empty", "Le calendrier ne contient encore aucun jalon.")
        return checks

    if AcademicCalendarEntry.EVENT_ACADEMIC_START not in event_types:
        add("error", "academic_start", "La rentree academique officielle est manquante.")
    if AcademicCalendarEntry.EVENT_ACADEMIC_END not in event_types:
        add("error", "academic_end", "La cloture academique officielle est manquante.")

    has_exam = AcademicCalendarEntry.EVENT_EXAM_SESSION in event_types
    has_retake = AcademicCalendarEntry.EVENT_RETAKE_SESSION in event_types
    has_results = AcademicCalendarEntry.EVENT_RESULT_PUBLICATION in event_types
    has_jury = AcademicCalendarEntry.EVENT_JURY in event_types
    if has_exam and not has_results:
        add("warning", "results", "Une session d'examens existe sans date previsionnelle de publication des resultats.")
    if has_results and not has_exam:
        add("warning", "exam_session", "Une publication de resultats existe sans session d'examens associee dans le calendrier.")
    if has_jury and not has_results:
        add("warning", "jury", "Un jury est programme avant toute publication de resultats dans le calendrier.")
    if has_retake and not has_exam:
        add("warning", "retake", "Un rattrapage est programme sans session normale identifiee.")

    try:
        _validate_no_entry_overlap(calendar)
    except ValidationError as exc:
        for message in exc.messages:
            add("error", "overlap", message)

    if not checks:
        add("success", "ready", "Les jalons structurants et leurs controles sont coherents.")
    return checks


@transaction.atomic
def publish_calendar(calendar, *, actor):
    require_calendar_access(actor, calendar)
    calendar = AcademicCalendar.objects.select_for_update().get(pk=calendar.pk)
    if calendar.status != AcademicCalendar.STATUS_VALIDATED:
        raise ValidationError("Seul un calendrier valide peut etre publie.")
    _validate_no_entry_overlap(calendar)
    AcademicCalendar.objects.select_for_update().filter(
        branch=calendar.branch,
        academic_year=calendar.academic_year,
        status=AcademicCalendar.STATUS_PUBLISHED,
    ).exclude(pk=calendar.pk).update(
        status=AcademicCalendar.STATUS_SUPERSEDED,
        updated_by=actor,
        updated_at=timezone.now(),
    )
    calendar.status = AcademicCalendar.STATUS_PUBLISHED
    calendar.published_by = actor
    calendar.published_at = timezone.now()
    calendar.updated_by = actor
    calendar.full_clean()
    calendar.save()
    calendar.entries.exclude(status=AcademicCalendarEntry.STATUS_CANCELLED).update(
        status=AcademicCalendarEntry.STATUS_PUBLISHED,
        updated_by=actor,
        updated_at=timezone.now(),
    )
    return calendar


@transaction.atomic
def create_calendar_revision(calendar, *, actor):
    """Clone une version publiee sans jamais ecraser son historique."""
    require_calendar_access(actor, calendar)
    calendar = AcademicCalendar.objects.select_for_update().get(pk=calendar.pk)
    if calendar.status != AcademicCalendar.STATUS_PUBLISHED:
        raise ValidationError("Seule une version publiee peut etre revisee.")
    next_version = (
        AcademicCalendar.objects.filter(
            branch=calendar.branch,
            academic_year=calendar.academic_year,
        )
        .order_by("-version")
        .values_list("version", flat=True)
        .first()
        or 0
    ) + 1
    revision = AcademicCalendar.objects.create(
        branch=calendar.branch,
        academic_year=calendar.academic_year,
        version=next_version,
        official_title=calendar.official_title,
        administrative_reference=calendar.administrative_reference,
        general_observations=calendar.general_observations,
        revision_of=calendar,
        status=AcademicCalendar.STATUS_DRAFT,
        created_by=actor,
        updated_by=actor,
    )
    entry_fields = [
        "title", "description", "event_type", "start_datetime", "end_datetime",
        "all_day", "target_scope", "programme", "academic_class", "semester",
        "color", "icon", "is_blocking",
    ]
    entries = []
    for entry in calendar.entries.all():
        values = {field: getattr(entry, field) for field in entry_fields}
        entries.append(
            AcademicCalendarEntry(
                calendar=revision,
                created_by=actor,
                updated_by=actor,
                status=AcademicCalendarEntry.STATUS_DRAFT,
                **values,
            )
        )
    for entry in entries:
        entry.full_clean()
    AcademicCalendarEntry.objects.bulk_create(entries)
    return revision


@transaction.atomic
def delete_calendar(calendar, *, actor):
    require_calendar_access(actor, calendar)
    if not _calendar_is_editable(calendar):
        raise ValidationError(
            "Seul un calendrier en brouillon peut etre supprime. "
            "Archivez-le d'abord s'il est publie."
        )
    calendar.entries.all().delete()
    calendar.delete()


@transaction.atomic
def archive_calendar(calendar, *, actor):
    require_calendar_access(actor, calendar)
    if calendar.status != AcademicCalendar.STATUS_PUBLISHED:
        raise ValidationError("Seul un calendrier publie peut etre archive.")
    calendar.status = AcademicCalendar.STATUS_ARCHIVED
    calendar.updated_by = actor
    calendar.full_clean()
    calendar.save()
    calendar.entries.update(
        status=AcademicCalendarEntry.STATUS_ARCHIVED,
        updated_by=actor,
        updated_at=timezone.now(),
    )
    return calendar


@transaction.atomic
def create_calendar_entry(*, actor, calendar, **data):
    require_calendar_access(actor, calendar)
    if not _calendar_is_editable(calendar):
        raise ValidationError("Seul un calendrier brouillon ou retourne peut recevoir des entrees.")
    entry = AcademicCalendarEntry(
        calendar=calendar,
        created_by=actor,
        updated_by=actor,
        **data,
    )
    entry.full_clean()
    entry.save()
    return entry


@transaction.atomic
def update_calendar_entry(entry, *, actor, **changes):
    require_calendar_access(actor, entry.calendar)
    if not _calendar_is_editable(entry.calendar):
        raise ValidationError("Seule l'entree d'un calendrier brouillon ou retourne peut etre modifiee.")
    _apply_changes(entry, changes, ENTRY_MUTABLE_FIELDS)
    entry.updated_by = actor
    entry.full_clean()
    entry.save()
    return entry


@transaction.atomic
def delete_calendar_entry(entry, *, actor):
    require_calendar_access(actor, entry.calendar)
    if not _calendar_is_editable(entry.calendar):
        raise ValidationError("Seule l'entree d'un calendrier brouillon ou retourne peut etre supprimee.")
    entry.delete()


@transaction.atomic
def report_calendar_disruption(*, actor, calendar, **data):
    """Declare une perturbation sans modifier le calendrier officiel."""
    require_calendar_access(actor, calendar)
    if calendar.status != AcademicCalendar.STATUS_PUBLISHED:
        raise ValidationError("Une perturbation ne peut etre declaree que sur le calendrier publie applicable.")
    disruption = AcademicCalendarDisruption(
        calendar=calendar,
        reported_by=actor,
        status=AcademicCalendarDisruption.STATUS_DRAFT,
        **data,
    )
    disruption.full_clean()
    disruption.save()
    return disruption


@transaction.atomic
def activate_calendar_disruption(disruption, *, actor):
    require_calendar_access(actor, disruption.calendar)
    if disruption.status != AcademicCalendarDisruption.STATUS_DRAFT:
        raise ValidationError("Seule une perturbation brouillon peut etre activee.")
    disruption.status = AcademicCalendarDisruption.STATUS_ACTIVE
    disruption.full_clean()
    disruption.save(update_fields=["status", "updated_at"])
    return disruption


@transaction.atomic
def close_calendar_disruption(disruption, *, actor, ends_at=None):
    require_calendar_access(actor, disruption.calendar)
    if disruption.status != AcademicCalendarDisruption.STATUS_ACTIVE:
        raise ValidationError("Seule une perturbation en cours peut etre cloturee.")
    if ends_at is not None:
        disruption.ends_at = ends_at
    if disruption.ends_at is None:
        raise ValidationError("La date de fin est obligatoire pour cloturer une perturbation.")
    disruption.status = AcademicCalendarDisruption.STATUS_CLOSED
    disruption.closed_by = actor
    disruption.closed_at = timezone.now()
    disruption.full_clean()
    disruption.save()
    return disruption


@transaction.atomic
def create_calendar_adjustment(*, actor, calendar, calendar_entry, action, reason,
                               disruption=None, effective_start_datetime=None,
                               effective_end_datetime=None, official_reference=""):
    """Prepare un avenant sans changer les dates de l'evenement de reference."""
    require_calendar_access(actor, calendar)
    if calendar.status != AcademicCalendar.STATUS_PUBLISHED:
        raise ValidationError("Un avenant ne peut viser que le calendrier publie applicable.")
    if calendar_entry.calendar_id != calendar.id:
        raise ValidationError("L'evenement choisi n'appartient pas au calendrier applicable.")
    if disruption is not None and disruption.calendar_id != calendar.id:
        raise ValidationError("La perturbation ne concerne pas ce calendrier.")
    adjustment = AcademicCalendarAdjustment(
        calendar=calendar,
        disruption=disruption,
        calendar_entry=calendar_entry,
        action=action,
        reason=(reason or "").strip(),
        previous_start_datetime=calendar_entry.start_datetime,
        previous_end_datetime=calendar_entry.end_datetime,
        effective_start_datetime=effective_start_datetime,
        effective_end_datetime=effective_end_datetime,
        official_reference=(official_reference or "").strip(),
        created_by=actor,
    )
    adjustment.full_clean()
    adjustment.save()
    return adjustment


@transaction.atomic
def submit_calendar_adjustment(adjustment, *, actor):
    require_calendar_access(actor, adjustment.calendar)
    if adjustment.status not in {
        AcademicCalendarAdjustment.STATUS_DRAFT,
        AcademicCalendarAdjustment.STATUS_REJECTED,
    }:
        raise ValidationError("Seul un avenant brouillon ou retourne peut etre soumis.")
    adjustment.status = AcademicCalendarAdjustment.STATUS_SUBMITTED
    adjustment.submitted_by = actor
    adjustment.full_clean()
    adjustment.save()
    return adjustment


@transaction.atomic
def validate_calendar_adjustment(adjustment, *, actor):
    require_calendar_access(actor, adjustment.calendar)
    if adjustment.status != AcademicCalendarAdjustment.STATUS_SUBMITTED:
        raise ValidationError("Seul un avenant soumis peut etre valide.")
    adjustment.status = AcademicCalendarAdjustment.STATUS_VALIDATED
    adjustment.validated_by = actor
    adjustment.full_clean()
    adjustment.save()
    return adjustment


@transaction.atomic
def publish_calendar_adjustment(adjustment, *, actor):
    require_calendar_access(actor, adjustment.calendar)
    if adjustment.status != AcademicCalendarAdjustment.STATUS_VALIDATED:
        raise ValidationError("Seul un avenant valide peut etre publie.")
    if adjustment.calendar.status != AcademicCalendar.STATUS_PUBLISHED:
        raise ValidationError("Le calendrier de reference n'est plus le calendrier publie applicable.")
    adjustment.status = AcademicCalendarAdjustment.STATUS_PUBLISHED
    adjustment.published_by = actor
    adjustment.published_at = timezone.now()
    adjustment.full_clean()
    adjustment.save()
    return adjustment


def get_effective_calendar_schedule(calendar):
    """Retourne la projection applicable : base publiee + avenants publies.

    Les entrees d'origine ne sont jamais modifiees par cette fonction.
    """
    entries = list(calendar.entries.exclude(status=AcademicCalendarEntry.STATUS_CANCELLED))
    adjustments = (
        AcademicCalendarAdjustment.objects.filter(
            calendar=calendar,
            status=AcademicCalendarAdjustment.STATUS_PUBLISHED,
        )
        .select_related("calendar_entry")
        .order_by("published_at", "id")
    )
    by_entry = {
        entry.id: {
            "entry": entry,
            "start_datetime": entry.start_datetime,
            "end_datetime": entry.end_datetime,
            "is_cancelled": False,
            "delivery_mode": "standard",
            "adjustments": [],
        }
        for entry in entries
    }
    for adjustment in adjustments:
        item = by_entry.get(adjustment.calendar_entry_id)
        if item is None:
            continue
        item["adjustments"].append(adjustment)
        if adjustment.action == AcademicCalendarAdjustment.ACTION_RESCHEDULE:
            item["start_datetime"] = adjustment.effective_start_datetime
            item["end_datetime"] = adjustment.effective_end_datetime
        elif adjustment.action == AcademicCalendarAdjustment.ACTION_CANCEL:
            item["is_cancelled"] = True
        elif adjustment.action == AcademicCalendarAdjustment.ACTION_ONLINE:
            item["delivery_mode"] = "online_continuity"
    return list(by_entry.values())


def get_disruption_impacts(disruption):
    """Liste les jalons potentiellement affectes par une perturbation locale.

    Cette analyse n'entraine jamais de changement automatique : elle sert a
    proposer au DE les seuls evenements qu'il doit examiner.
    """
    end_datetime = disruption.ends_at
    if end_datetime is None:
        end_datetime = timezone.make_aware(
            datetime.combine(disruption.calendar.academic_year.end_date, datetime.max.time())
        )
    entries = (
        disruption.calendar.entries
        .exclude(status=AcademicCalendarEntry.STATUS_CANCELLED)
        .filter(
            start_datetime__lt=end_datetime,
            end_datetime__gt=disruption.starts_at,
        )
        .select_related("programme", "academic_class", "semester", "semester__academic_class")
        .order_by("start_datetime", "id")
    )
    return [entry for entry in entries if _target_scope_overlaps(disruption, entry)]


def assert_course_not_blocked(*, branch, academic_year, academic_class, start_datetime, end_datetime):
    scope = Q(target_scope=AcademicCalendarEntry.SCOPE_BRANCH)
    if academic_class is not None:
        scope |= Q(target_scope=AcademicCalendarEntry.SCOPE_PROGRAMME, programme=academic_class.programme)
        scope |= Q(target_scope=AcademicCalendarEntry.SCOPE_CLASS, academic_class=academic_class)
        scope |= Q(target_scope=AcademicCalendarEntry.SCOPE_SEMESTER, semester__academic_class=academic_class)
    conflict = (
        AcademicCalendarEntry.objects.filter(
            calendar__branch=branch,
            calendar__academic_year=academic_year,
            calendar__status=AcademicCalendar.STATUS_PUBLISHED,
            status=AcademicCalendarEntry.STATUS_PUBLISHED,
            is_blocking=True,
            start_datetime__lt=end_datetime,
            end_datetime__gt=start_datetime,
        )
        .filter(scope)
        .first()
    )
    if conflict:
        raise ValidationError(f"Cours impossible pendant la periode bloquante : {conflict.title}.")
