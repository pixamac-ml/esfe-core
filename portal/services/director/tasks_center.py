"""Centre de taches pedagogique du dashboard Directeur des Etudes.

Agrege en une liste unique les points qui necessitent une action du
directeur, pour eviter de naviguer manuellement entre les 12 sections du
dashboard (cf. CAHIER_DES_CHARGES_DIRECTEUR_ETUDES.md, 2.3). Reutilise les
donnees deja calculees par `_build_director_workspace_context()` plutot que
de les recalculer.
"""
from academics.models import Semester
from portal.models import TransferRequest, TeacherDocument

LEVEL_CRITICAL = "critical"
LEVEL_WARNING = "warning"
LEVEL_INFO = "info"
LEVEL_ORDER = {LEVEL_CRITICAL: 0, LEVEL_WARNING: 1, LEVEL_INFO: 2}


def _task(category, count, level, message, *, target, action_label="Traiter"):
    return {
        "category": category,
        "count": count,
        "level": level,
        "message": message,
        "target": target,
        "action_label": action_label,
    }


def build_director_tasks_center(*, branch, semester_rows, teacher_unassigned_count, result_anomalies):
    tasks = []

    entry_in_progress = [row for row in semester_rows if row["semester"].status == Semester.STATUS_NORMAL_ENTRY]
    if entry_in_progress:
        tasks.append(_task(
            "grades_entry_in_progress",
            len(entry_in_progress),
            LEVEL_WARNING,
            f"{len(entry_in_progress)} classe(s) en cours de saisie de notes (session normale).",
            target="results",
            action_label="Voir les resultats",
        ))

    if teacher_unassigned_count:
        tasks.append(_task(
            "teachers_unassigned",
            teacher_unassigned_count,
            LEVEL_WARNING,
            f"{teacher_unassigned_count} enseignant(s) sans aucune affectation pour l'annee en cours.",
            target="teachers",
            action_label="Voir les enseignants",
        ))

    ready_to_validate = [row for row in semester_rows if row["can_validate"]]
    if ready_to_validate:
        tasks.append(_task(
            "semesters_ready_to_validate",
            len(ready_to_validate),
            LEVEL_CRITICAL,
            f"{len(ready_to_validate)} semestre(s) prets a etre valides (toutes les notes sont saisies).",
            target="results",
            action_label="Valider",
        ))

    pending_documents = TeacherDocument.objects.filter(branch=branch, is_verified=False).count() if branch else 0
    if pending_documents:
        tasks.append(_task(
            "documents_pending",
            pending_documents,
            LEVEL_WARNING,
            f"{pending_documents} document(s) enseignant en attente de verification.",
            target="documents",
            action_label="Verifier",
        ))

    pending_transfers = (
        TransferRequest.objects.filter(branch=branch, status=TransferRequest.STATUS_SUBMITTED).count() if branch else 0
    )
    if pending_transfers:
        tasks.append(_task(
            "transfers_pending",
            pending_transfers,
            LEVEL_WARNING,
            f"{pending_transfers} demande(s) de transfert en attente de decision.",
            target="documents",
            action_label="Decider",
        ))

    if result_anomalies:
        blocking_count = sum(1 for anomaly in result_anomalies if anomaly.get("level") == "blocking")
        level = LEVEL_CRITICAL if blocking_count else LEVEL_INFO
        tasks.append(_task(
            "result_anomalies",
            len(result_anomalies),
            level,
            f"{len(result_anomalies)} anomalie(s) de notes detectee(s) ({blocking_count} bloquante(s)).",
            target="results",
            action_label="Examiner",
        ))

    tasks.sort(key=lambda item: (LEVEL_ORDER.get(item["level"], 3), -item["count"]))
    return tasks
