from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db.models import Count, Q

from academics.models import AcademicEnrollment, ECGrade, Semester
from academics.services.semester import compute_semester_result
from accounts.dashboards.helpers import get_user_branch
from portal.models import SupportAuditLog
from portal.services.it_support_service import log_support_action


STATE_EMPTY = "empty"
STATE_IN_PROGRESS = "in_progress"
STATE_READY_TO_CALCULATE = "ready_to_calculate"
STATE_CALCULATED = "calculated"
STATE_SENT_TO_DIRECTOR = "sent_to_director"

ACTION_START = "start_saisie"
ACTION_CONTINUE = "continue_saisie"
ACTION_VERIFY = "verifier_notes"
ACTION_CALCULATE = "calculer_resultats"
ACTION_SEND_TO_DIRECTOR = "envoyer_direction"


@dataclass(frozen=True)
class NotesWorkflowState:
    code: str
    label: str
    description: str
    entered_grades: int
    expected_grades: int
    progress_percent: int
    missing_grades: int
    semester_status: str
    technical_alerts: list[str]


STATE_LABELS = {
    STATE_EMPTY: "Non commence",
    STATE_IN_PROGRESS: "Saisie en cours",
    STATE_READY_TO_CALCULATE: "Notes completes - resultats calculables",
    STATE_CALCULATED: "Resultats calcules",
    STATE_SENT_TO_DIRECTOR: "Publies par Directeur",
}


def get_notes_state(*, academic_class, semester) -> NotesWorkflowState | None:
    if not academic_class or not semester:
        return None

    enrollments = AcademicEnrollment.objects.filter(
        academic_class=academic_class,
        academic_year=academic_class.academic_year,
        is_active=True,
    )
    enrollment_count = enrollments.count()
    ec_count = semester.ues.aggregate(total=Count("ecs", distinct=True))["total"] or 0
    expected_grades = enrollment_count * ec_count
    entered_grades = ECGrade.objects.filter(
        enrollment__in=enrollments,
        ec__ue__semester=semester,
    ).filter(
        Q(normal_score__isnull=False) | Q(retake_score__isnull=False) | Q(final_score__isnull=False)
    ).count()
    progress_percent = int((entered_grades / expected_grades) * 100) if expected_grades else 0

    missing_grades = max(expected_grades - entered_grades, 0)

    if semester.status == Semester.STATUS_PUBLISHED:
        code = STATE_SENT_TO_DIRECTOR
    elif semester.status == Semester.STATUS_FINALIZED:
        code = STATE_CALCULATED
    elif expected_grades and entered_grades >= expected_grades:
        code = STATE_READY_TO_CALCULATE
    elif entered_grades:
        code = STATE_IN_PROGRESS
    else:
        code = STATE_EMPTY

    descriptions = {
        STATE_EMPTY: "Aucune note exploitable. Demarrer la saisie pour cette classe et ce semestre.",
        STATE_IN_PROGRESS: "Des notes existent deja. Completer les cellules manquantes avant calcul.",
        STATE_READY_TO_CALCULATE: "Toutes les notes attendues sont renseignees. Les resultats peuvent etre generes.",
        STATE_CALCULATED: "Les moyennes et credits ont ete recalcules avec le moteur academique existant.",
        STATE_SENT_TO_DIRECTOR: "Les releves sont disponibles selon le statut publie du semestre.",
    }
    technical_alerts = []
    if not enrollment_count:
        technical_alerts.append("Aucune inscription academique active dans cette classe.")
    if not ec_count:
        technical_alerts.append("Aucun EC n'est rattache a ce semestre.")
    if missing_grades:
        technical_alerts.append(f"{missing_grades} note(s) manquante(s) dans la grille.")

    return NotesWorkflowState(
        code=code,
        label=STATE_LABELS[code],
        description=descriptions[code],
        entered_grades=entered_grades,
        expected_grades=expected_grades,
        progress_percent=min(progress_percent, 100),
        missing_grades=missing_grades,
        semester_status=semester.status,
        technical_alerts=technical_alerts,
    )


def get_available_actions(*, state: NotesWorkflowState | None):
    if state is None:
        return []
    actions_by_state = {
        STATE_EMPTY: [
            {"code": ACTION_START, "label": "Demarrer la saisie", "style": "primary"},
        ],
        STATE_IN_PROGRESS: [
            {"code": ACTION_VERIFY, "label": "Verifier les notes", "style": "secondary"},
            {"code": ACTION_CONTINUE, "label": "Continuer la saisie", "style": "primary"},
        ],
        STATE_READY_TO_CALCULATE: [
            {"code": ACTION_VERIFY, "label": "Verifier les notes", "style": "secondary"},
            {"code": ACTION_CALCULATE, "label": "Calculer / Generer les resultats", "style": "primary"},
        ],
        STATE_CALCULATED: [
            {"code": ACTION_SEND_TO_DIRECTOR, "label": "Envoyer a la direction", "style": "primary"},
        ],
        STATE_SENT_TO_DIRECTOR: [],
    }
    return actions_by_state.get(state.code, [])


def apply_notes_workflow_action(*, actor, academic_class, semester, action):
    state = get_notes_state(academic_class=academic_class, semester=semester)
    if state is None:
        raise ValidationError("Selection classe/semestre invalide.")

    if action == ACTION_START:
        if semester.status == Semester.STATUS_DRAFT:
            semester.status = Semester.STATUS_NORMAL_ENTRY
            semester.save(update_fields=["status"])
        return

    if action == ACTION_CONTINUE:
        if semester.status == Semester.STATUS_DRAFT:
            semester.status = Semester.STATUS_NORMAL_ENTRY
            semester.save(update_fields=["status"])
        return

    if action == ACTION_VERIFY:
        if state.missing_grades:
            raise ValidationError(f"{state.missing_grades} note(s) manquante(s). Le calcul reste bloque.")
        return

    if action == ACTION_CALCULATE:
        if state.code != STATE_READY_TO_CALCULATE:
            raise ValidationError("Toutes les notes doivent etre renseignees avant de generer les resultats.")
        enrollments = AcademicEnrollment.objects.filter(
            academic_class=academic_class,
            academic_year=academic_class.academic_year,
            is_active=True,
        )
        for enrollment in enrollments:
            compute_semester_result(semester, enrollment)
        semester.status = Semester.STATUS_FINALIZED
        semester.save(update_fields=["status"])
        log_support_action(
            actor=actor,
            branch=get_user_branch(actor),
            action_type=SupportAuditLog.ACTION_RESULTS_CALCULATED,
            target_label=f"Resultats {academic_class.display_name} S{semester.number}",
            details=f"{enrollments.count()} etudiant(s) recalcules depuis le dashboard informaticien.",
        )
        return

    if action == ACTION_SEND_TO_DIRECTOR:
        if state.code != STATE_CALCULATED:
            raise ValidationError("Les resultats doivent etre calcules avant transmission.")
        semester.status = Semester.STATUS_PUBLISHED
        semester.save(update_fields=["status"])
        log_support_action(
            actor=actor,
            branch=get_user_branch(actor),
            action_type=SupportAuditLog.ACTION_RESULTS_SENT,
            target_label=f"Transmission {academic_class.display_name} S{semester.number}",
            details="Resultats marques comme envoyes au Directeur des Etudes.",
        )
        return

    raise ValidationError("Action workflow inconnue.")
