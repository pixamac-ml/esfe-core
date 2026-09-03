"""Règles métier des dossiers opérationnels d'évaluation."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from academics.models import (
    AcademicCalendar,
    AcademicCalendarEntry,
    AcademicClass,
    EC,
    EvaluationCampaign,
    EvaluationCampaignScope,
    EvaluationRequirement,
    Semester,
)


def _eligible_classes(entry):
    queryset = AcademicClass.objects.filter(
        branch=entry.calendar.branch,
        academic_year=entry.calendar.academic_year,
        is_active=True,
    )
    if entry.target_scope == AcademicCalendarEntry.SCOPE_PROGRAMME:
        return queryset.filter(programme=entry.programme)
    if entry.target_scope == AcademicCalendarEntry.SCOPE_CLASS:
        return queryset.filter(pk=entry.academic_class_id)
    if entry.target_scope == AcademicCalendarEntry.SCOPE_SEMESTER:
        return queryset.filter(pk=entry.semester.academic_class_id)
    return queryset


@transaction.atomic
def create_evaluation_campaign(*, actor, calendar_entry, title="", publication_entry=None, semester_number=None):
    """Ouvre un dossier depuis un jalon publié, sans créer d'épreuve automatiquement."""
    if calendar_entry.calendar.status not in {AcademicCalendar.STATUS_VALIDATED, AcademicCalendar.STATUS_PUBLISHED}:
        raise ValidationError("Validez le calendrier avant d'ouvrir une campagne d'évaluation.")
    allowed_entry_statuses = {AcademicCalendarEntry.STATUS_PUBLISHED}
    if calendar_entry.calendar.status == AcademicCalendar.STATUS_VALIDATED:
        allowed_entry_statuses.add(AcademicCalendarEntry.STATUS_DRAFT)
    if calendar_entry.status not in allowed_entry_statuses:
        raise ValidationError("Le jalon de session doit être disponible dans le calendrier validé.")
    kind_map = {
        AcademicCalendarEntry.EVENT_EXAM_SESSION: EvaluationCampaign.KIND_NORMAL,
        AcademicCalendarEntry.EVENT_RETAKE_SESSION: EvaluationCampaign.KIND_RETAKE,
    }
    kind = kind_map.get(calendar_entry.event_type)
    if kind is None:
        raise ValidationError("Seul un jalon d'examens ou de rattrapage peut ouvrir une campagne.")
    if EvaluationCampaign.objects.filter(calendar_entry=calendar_entry).exclude(status=EvaluationCampaign.STATUS_CANCELLED).exists():
        raise ValidationError("Une campagne active existe déjà pour ce jalon.")
    if semester_number is not None:
        if semester_number < 1:
            raise ValidationError("Le semestre sélectionné est invalide.")
        if not Semester.objects.filter(
            academic_class__in=_eligible_classes(calendar_entry), number=semester_number
        ).exists():
            raise ValidationError("Ce semestre n'est pas configuré pour la portée de ce calendrier.")
    if publication_entry is not None:
        if publication_entry.calendar_id != calendar_entry.calendar_id:
            raise ValidationError("Le jalon de publication doit appartenir au même calendrier.")
        if publication_entry.event_type != AcademicCalendarEntry.EVENT_RESULT_PUBLICATION:
            raise ValidationError("Le jalon sélectionné n'est pas une publication de résultats.")

    campaign = EvaluationCampaign(
        branch=calendar_entry.calendar.branch,
        academic_year=calendar_entry.calendar.academic_year,
        calendar_entry=calendar_entry,
        result_publication_entry=publication_entry,
        kind=kind,
        semester_number=semester_number,
        title=title.strip() or calendar_entry.title,
        created_by=actor,
    )
    campaign.full_clean()
    campaign.save()
    fixed_semester = calendar_entry.semester if calendar_entry.target_scope == AcademicCalendarEntry.SCOPE_SEMESTER else None
    for academic_class in _eligible_classes(calendar_entry):
        scope_semester = fixed_semester
        if scope_semester is None and semester_number:
            scope_semester = Semester.objects.filter(academic_class=academic_class, number=semester_number).first()
        scope = EvaluationCampaignScope(campaign=campaign, academic_class=academic_class, semester=scope_semester)
        scope.full_clean()
        scope.save()
    populate_campaign_requirements(campaign=campaign)
    return campaign


@transaction.atomic
def populate_campaign_requirements(*, campaign):
    """Prépare les EC à évaluer et leurs seuils J-7/J-3 sans envoyer de relance."""
    due_at = campaign.calendar_entry.start_datetime - timedelta(days=7)
    critical_at = campaign.calendar_entry.start_datetime - timedelta(days=3)
    scopes = campaign.scopes.filter(included=True).select_related("academic_class", "semester")
    for scope in scopes:
        ecs = EC.objects.filter(ue__semester__academic_class=scope.academic_class)
        if scope.semester_id:
            ecs = ecs.filter(ue__semester=scope.semester)
        elif campaign.semester_number:
            ecs = ecs.filter(ue__semester__number=campaign.semester_number)
        for ec in ecs.select_related("ue__semester"):
            EvaluationRequirement.objects.get_or_create(
                campaign=campaign,
                academic_class=scope.academic_class,
                ec=ec,
                defaults={"subject_due_at": due_at, "critical_at": critical_at},
            )


def assert_event_in_campaign_window(*, campaign, start_datetime, end_datetime):
    """Une épreuve respecte la période effective du calendrier, sauf dérogation motivée."""
    if timezone.is_naive(start_datetime) or timezone.is_naive(end_datetime):
        raise ValidationError("Les dates de l'épreuve doivent inclure une timezone.")
    start = timezone.localtime(start_datetime)
    end = timezone.localtime(end_datetime)
    entry = campaign.calendar_entry
    if start < timezone.localtime(entry.start_datetime) or end > timezone.localtime(entry.end_datetime):
        if not campaign.exception_reason.strip():
            raise ValidationError("L'épreuve doit rester dans la période officielle de la campagne.")
