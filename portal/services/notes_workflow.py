from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db.models import Count

from academics.models import AcademicEnrollment, ECGrade, Semester
from academics.services.grading import compute_ec_status
from academics.services.semester import compute_semester_result
from accounts.dashboards.helpers import get_user_branch
from portal.models import SupportAuditLog
from portal.services.it_support_service import log_support_action


STATE_EMPTY = "empty"
STATE_IN_PROGRESS = "in_progress"
STATE_READY_TO_PUBLISH_NORMAL = "ready_to_publish_normal"
STATE_NORMAL_PUBLISHED = "normal_published"
STATE_RETAKE_IN_PROGRESS = "retake_in_progress"
STATE_READY_TO_PUBLISH_FINAL = "ready_to_publish_final"
STATE_FINAL_PUBLISHED = "final_published"

ACTION_START = "start_saisie"
ACTION_CONTINUE = "continue_saisie"
ACTION_VERIFY = "verifier_notes"
ACTION_PUBLISH_NORMAL = "publier_session_normale"
ACTION_PREVIEW_RETAKE = "ouvrir_rattrapage"
ACTION_ACTIVATE_RETAKE = "activer_rattrapage"
ACTION_PUBLISH_FINAL = "publier_resultats_finaux"


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
    retake_candidates_count: int
    retake_subjects_count: int
    retake_ready: bool
    final_publish_ready: bool


@dataclass(frozen=True)
class RetakeCandidate:
    enrollment_id: int
    student_id: int
    student_name: str
    average: object
    failed_subjects: list[dict]


STATE_LABELS = {
    STATE_EMPTY: "Non commence",
    STATE_IN_PROGRESS: "Saisie en cours",
    STATE_READY_TO_PUBLISH_NORMAL: "Session normale prete a publier",
    STATE_NORMAL_PUBLISHED: "Session normale publiee",
    STATE_RETAKE_IN_PROGRESS: "Rattrapage actif",
    STATE_READY_TO_PUBLISH_FINAL: "Resultats finaux prets",
    STATE_FINAL_PUBLISHED: "Resultats finaux publies",
}


def get_retake_candidates(*, academic_class, semester) -> list[RetakeCandidate]:
    if not academic_class or not semester:
        return []

    threshold = academic_class.validation_threshold or 10
    enrollments = list(
        AcademicEnrollment.objects.select_related(
            "student__student_profile__inscription__candidature",
        ).filter(
            academic_class=academic_class,
            academic_year=academic_class.academic_year,
            is_active=True,
        )
    )
    grades = list(
        ECGrade.objects.select_related("ec", "ec__ue")
        .filter(
            enrollment__in=enrollments,
            ec__ue__semester=semester,
        )
        .order_by("ec__ue__code", "ec__title")
    )
    grades_by_enrollment: dict[int, list[ECGrade]] = {}
    for grade in grades:
        grades_by_enrollment.setdefault(grade.enrollment_id, []).append(grade)

    candidates: list[RetakeCandidate] = []
    for enrollment in enrollments:
        failed_subjects = []
        for grade in grades_by_enrollment.get(enrollment.id, []):
            normal_status = compute_ec_status(grade.normal_score, threshold)
            if normal_status != "failed" and grade.retake_score is None:
                continue
            failed_subjects.append(
                {
                    "ec_id": grade.ec_id,
                    "ue_code": grade.ec.ue.code,
                    "ec_title": grade.ec.title,
                    "normal_score": grade.normal_score,
                    "retake_score": grade.retake_score,
                    "final_score": grade.final_score,
                    "is_retake_entered": grade.retake_score is not None,
                }
            )
        if not failed_subjects:
            continue
        semester_summary = compute_semester_result(semester, enrollment)
        candidates.append(
            RetakeCandidate(
                enrollment_id=enrollment.id,
                student_id=enrollment.student_id,
                student_name=enrollment.student.student_profile.full_name,
                average=semester_summary["average"],
                failed_subjects=failed_subjects,
            )
        )
    return candidates


def can_edit_retake_grade(*, grade, threshold):
    if grade is None:
        return False
    if grade.retake_score is not None:
        return True
    return compute_ec_status(grade.normal_score, threshold) == "failed"


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
        normal_score__isnull=False,
    ).count()
    progress_percent = int((entered_grades / expected_grades) * 100) if expected_grades else 0

    missing_grades = max(expected_grades - entered_grades, 0)

    retake_candidates = get_retake_candidates(academic_class=academic_class, semester=semester)
    retake_subjects_count = sum(len(candidate.failed_subjects) for candidate in retake_candidates)

    if semester.status == Semester.STATUS_PUBLISHED:
        code = STATE_FINAL_PUBLISHED
    elif semester.status == Semester.STATUS_FINALIZED:
        code = STATE_READY_TO_PUBLISH_FINAL
    elif semester.status == Semester.STATUS_RETAKE_ENTRY:
        code = STATE_RETAKE_IN_PROGRESS
    elif semester.status == Semester.STATUS_NORMAL_LOCKED:
        code = STATE_NORMAL_PUBLISHED
    elif expected_grades and entered_grades >= expected_grades:
        code = STATE_READY_TO_PUBLISH_NORMAL
    elif entered_grades:
        code = STATE_IN_PROGRESS
    else:
        code = STATE_EMPTY

    descriptions = {
        STATE_EMPTY: "Aucune note exploitable. Demarrer la saisie pour cette classe et ce semestre.",
        STATE_IN_PROGRESS: "Des notes existent deja. Completer les cellules manquantes avant calcul.",
        STATE_READY_TO_PUBLISH_NORMAL: "Toutes les notes normales sont renseignees. La session normale peut etre publiee.",
        STATE_NORMAL_PUBLISHED: "La session normale est publiee. Le rattrapage peut maintenant etre prepare.",
        STATE_RETAKE_IN_PROGRESS: "Le rattrapage est actif. Les notes normales restent visibles et seules les notes de rattrapage doivent etre ajustees.",
        STATE_READY_TO_PUBLISH_FINAL: "Le semestre est finalise et pret pour publication finale.",
        STATE_FINAL_PUBLISHED: "Les releves et exports finaux sont deblocables selon les regles du semestre.",
    }
    technical_alerts = []
    if not enrollment_count:
        technical_alerts.append("Aucune inscription academique active dans cette classe.")
    if not ec_count:
        technical_alerts.append("Aucun EC n'est rattache a ce semestre.")
    if missing_grades:
        technical_alerts.append(f"{missing_grades} note(s) manquante(s) dans la grille.")
    if retake_candidates:
        technical_alerts.append(f"{len(retake_candidates)} etudiant(s) ont un rattrapage potentiel sur {retake_subjects_count} matiere(s).")

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
        retake_candidates_count=len(retake_candidates),
        retake_subjects_count=retake_subjects_count,
        retake_ready=semester.status == Semester.STATUS_NORMAL_LOCKED and bool(retake_candidates),
        final_publish_ready=semester.status in {Semester.STATUS_RETAKE_ENTRY, Semester.STATUS_NORMAL_LOCKED, Semester.STATUS_FINALIZED},
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
        STATE_READY_TO_PUBLISH_NORMAL: [
            {"code": ACTION_VERIFY, "label": "Verifier les notes", "style": "secondary"},
            {"code": ACTION_PUBLISH_NORMAL, "label": "Publier session normale", "style": "primary"},
        ],
        STATE_NORMAL_PUBLISHED: (
            [{"code": ACTION_PREVIEW_RETAKE, "label": "Ouvrir rattrapage", "style": "secondary", "kind": "modal"}]
            if state.retake_ready
            else []
        ) + [
            {"code": ACTION_PUBLISH_FINAL, "label": "Publier resultats finaux", "style": "primary"},
        ],
        STATE_RETAKE_IN_PROGRESS: [
            {"code": ACTION_PUBLISH_FINAL, "label": "Publier resultats finaux", "style": "primary"},
        ],
        STATE_READY_TO_PUBLISH_FINAL: [
            {"code": ACTION_PUBLISH_FINAL, "label": "Publier resultats finaux", "style": "primary"},
        ],
        STATE_FINAL_PUBLISHED: [],
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

    if action == ACTION_PUBLISH_NORMAL:
        if state.code != STATE_READY_TO_PUBLISH_NORMAL:
            raise ValidationError("Toutes les notes normales doivent etre renseignees avant publication.")
        enrollments = AcademicEnrollment.objects.filter(
            academic_class=academic_class,
            academic_year=academic_class.academic_year,
            is_active=True,
        )
        for enrollment in enrollments:
            compute_semester_result(semester, enrollment)
        semester.status = Semester.STATUS_NORMAL_LOCKED
        semester.save(update_fields=["status"])
        log_support_action(
            actor=actor,
            branch=get_user_branch(actor),
            action_type=SupportAuditLog.ACTION_RESULTS_CALCULATED,
            target_label=f"Publication normale {academic_class.display_name} S{semester.number}",
            details=f"Session normale publiee pour {enrollments.count()} etudiant(s).",
        )
        return

    if action == ACTION_PREVIEW_RETAKE:
        return

    if action == ACTION_ACTIVATE_RETAKE:
        if semester.status != Semester.STATUS_NORMAL_LOCKED:
            raise ValidationError("Le rattrapage ne peut etre active qu'apres publication de la session normale.")
        if not get_retake_candidates(academic_class=academic_class, semester=semester):
            raise ValidationError("Aucun etudiant n'est concerne par le rattrapage.")
        semester.status = Semester.STATUS_RETAKE_ENTRY
        semester.save(update_fields=["status"])
        log_support_action(
            actor=actor,
            branch=get_user_branch(actor),
            action_type=SupportAuditLog.ACTION_RESULTS_SENT,
            target_label=f"Activation rattrapage {academic_class.display_name} S{semester.number}",
            details="Rattrapage active depuis le dashboard informaticien.",
        )
        return

    if action == ACTION_PUBLISH_FINAL:
        if semester.status not in {Semester.STATUS_NORMAL_LOCKED, Semester.STATUS_RETAKE_ENTRY, Semester.STATUS_FINALIZED}:
            raise ValidationError("La publication finale n'est pas autorisee a ce stade.")
        enrollments = AcademicEnrollment.objects.filter(
            academic_class=academic_class,
            academic_year=academic_class.academic_year,
            is_active=True,
        )
        for enrollment in enrollments:
            compute_semester_result(semester, enrollment)
        semester.status = Semester.STATUS_PUBLISHED
        semester.save(update_fields=["status"])
        log_support_action(
            actor=actor,
            branch=get_user_branch(actor),
            action_type=SupportAuditLog.ACTION_RESULTS_SENT,
            target_label=f"Publication finale {academic_class.display_name} S{semester.number}",
            details=f"Resultats finaux publies pour {enrollments.count()} etudiant(s).",
        )
        return

    raise ValidationError("Action workflow inconnue.")
