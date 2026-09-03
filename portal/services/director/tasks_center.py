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


def _task(
    category,
    count,
    level,
    message,
    *,
    target,
    subview="overview",
    action_label="Traiter",
):
    return {
        "category": category,
        "count": count,
        "level": level,
        "message": message,
        "target": target,
        "subview": subview,
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
            f"{len(entry_in_progress)} classe(s) en cours de saisie de notes pour la session normale.",
            target="evaluations",
            action_label="Contrôler les notes",
        ))

    if teacher_unassigned_count:
        tasks.append(_task(
            "teachers_unassigned",
            teacher_unassigned_count,
            LEVEL_WARNING,
            f"{teacher_unassigned_count} enseignant(s) sans affectation pour l'année en cours.",
            target="enseignants",
            subview="assignments",
            action_label="Gérer les affectations",
        ))

    ready_to_validate = [row for row in semester_rows if row["can_validate"]]
    if ready_to_validate:
        tasks.append(_task(
            "semesters_ready_to_validate",
            len(ready_to_validate),
            LEVEL_CRITICAL,
            f"{len(ready_to_validate)} semestre(s) prêt(s) à être validé(s) : toutes les notes sont saisies.",
            target="evaluations",
            subview="validation",
            action_label="Ouvrir la validation",
        ))

    pending_documents = TeacherDocument.objects.filter(branch=branch, is_verified=False).count() if branch else 0
    if pending_documents:
        tasks.append(_task(
            "documents_pending",
            pending_documents,
            LEVEL_WARNING,
            f"{pending_documents} document(s) enseignant en attente de vérification.",
            target="enseignants",
            subview="files",
            action_label="Vérifier les dossiers",
        ))

    pending_transfers = (
        TransferRequest.objects.filter(branch=branch, status=TransferRequest.STATUS_SUBMITTED).count() if branch else 0
    )
    if pending_transfers:
        tasks.append(_task(
            "transfers_pending",
            pending_transfers,
            LEVEL_WARNING,
            f"{pending_transfers} demande(s) de transfert en attente de décision.",
            target="transferts",
            subview="pending",
            action_label="Traiter les demandes",
        ))

    if result_anomalies:
        blocking_count = sum(1 for anomaly in result_anomalies if anomaly.get("level") == "blocking")
        level = LEVEL_CRITICAL if blocking_count else LEVEL_INFO
        tasks.append(_task(
            "result_anomalies",
            len(result_anomalies),
            level,
            f"{len(result_anomalies)} anomalie(s) de notes détectée(s), dont {blocking_count} bloquante(s).",
            target="evaluations",
            action_label="Examiner les anomalies",
        ))

    tasks.sort(key=lambda item: (LEVEL_ORDER.get(item["level"], 3), -item["count"]))
    return tasks
