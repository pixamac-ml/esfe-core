from __future__ import annotations

from academics.permissions.timetable_permissions import require_timetable_access
from academics.selectors.director_monitoring_selectors import (
    get_course_progress,
    get_exam_events,
    get_monitoring_classes,
    get_monitoring_semesters,
    get_results_summary,
    get_teacher_absences,
)
from academics.services.academic_readiness_service import build_semester_readiness
from academics.services.timetable_management_service import build_timetable_overview


STATUS_OK = "OK"
STATUS_ATTENTION = "Attention"
STATUS_BLOCKED = "Bloqué"

COLORS = {STATUS_OK: "green", STATUS_ATTENTION: "amber", STATUS_BLOCKED: "red"}


def _indicator(status, message, action, **data):
    return {
        "status": status,
        "statut": status,
        "color": COLORS[status],
        "couleur": COLORS[status],
        "message": message,
        "recommended_action": action,
        "action_recommandee": action,
        **data,
    }


def _map_readiness(section):
    status = {
        "ok": STATUS_OK,
        "warning": STATUS_ATTENTION,
        "blocked": STATUS_BLOCKED,
    }.get(section.get("status"), STATUS_ATTENTION)
    return _indicator(
        status,
        section.get("message", "Etat non disponible."),
        section.get("action", "Verifier la configuration."),
    )


def _overall_status(indicators):
    statuses = {item["status"] for item in indicators.values()}
    if STATUS_BLOCKED in statuses:
        return STATUS_BLOCKED
    if STATUS_ATTENTION in statuses:
        return STATUS_ATTENTION
    return STATUS_OK


def build_director_semester_monitoring(*, actor, semester, week_start=None):
    """Construit une synthese strictement en lecture seule pour un semestre."""
    academic_class = semester.academic_class
    require_timetable_access(actor, academic_class.branch)

    readiness = build_semester_readiness(actor=actor, semester=semester)
    timetable = build_timetable_overview(actor=actor, academic_class=academic_class, week_start=week_start)
    progress = get_course_progress(semester=semester)
    absences = get_teacher_absences(semester=semester)
    exams = get_exam_events(semester=semester)
    results = get_results_summary(semester=semester)

    indicators = {
        "calendrier": _map_readiness(readiness["calendrier"]),
        "programmes_ue_ec": _map_readiness(readiness["programme"]),
        "affectations_enseignants": _map_readiness(readiness["enseignants"]),
        "emploi_du_temps": _map_readiness(readiness["emploi_du_temps"]),
        "progression_cours": _indicator(
            STATUS_OK if not progress["not_completed_courses"] and not progress["postponed_courses"] else STATUS_ATTENTION,
            f"{progress['completed_courses']} cours realises sur {progress['planned_courses']} planifies.",
            "Aucune action." if not progress["not_completed_courses"] else "Verifier les cours non realises.",
            **progress,
        ),
        "enseignants_absents": _indicator(
            STATUS_ATTENTION if absences.exists() else STATUS_OK,
            f"{absences.count()} absence(s) enseignant enregistree(s).",
            "Planifier les rattrapages." if absences.exists() else "Aucune action.",
            count=absences.count(),
        ),
        "volumes_horaires": _indicator(
            STATUS_ATTENTION if progress["remaining_hours"] else STATUS_OK,
            f"{progress['completed_hours']} h realisees, {progress['remaining_hours']} h restantes.",
            "Suivre le volume restant." if progress["remaining_hours"] else "Aucune action.",
            completed_hours=progress["completed_hours"],
            remaining_hours=progress["remaining_hours"],
        ),
        "examens": _indicator(
            STATUS_OK if exams.exists() else STATUS_BLOCKED,
            f"{exams.count()} examen(s) planifie(s)." if exams.exists() else "Aucun examen planifie.",
            "Aucune action." if exams.exists() else "Planifier les examens.",
            count=exams.count(),
        ),
        "notes_importees": _indicator(
            STATUS_OK if results["imported_grades"] else STATUS_ATTENTION,
            f"{results['imported_grades']} note(s) importee(s).",
            "Aucune action." if results["imported_grades"] else "Verifier l'import avec l'Informaticien.",
            count=results["imported_grades"],
        ),
        "resultats_valides": _indicator(
            STATUS_OK if results["validated_results"] else STATUS_ATTENTION,
            f"{results['validated_results']} resultat(s) valide(s).",
            "Aucune action." if results["validated_results"] else "Suivre la validation des resultats.",
            count=results["validated_results"],
        ),
        "bulletins_publies": _indicator(
            STATUS_OK if results["published_bulletins"] else STATUS_ATTENTION,
            f"{results['published_bulletins']} bulletin(s) publie(s).",
            "Aucune action." if results["published_bulletins"] else "Suivre la publication des bulletins.",
            count=results["published_bulletins"],
        ),
    }
    blocking_alerts = [item for item in indicators.values() if item["status"] == STATUS_BLOCKED]
    anomalies = [item for item in indicators.values() if item["status"] == STATUS_ATTENTION]
    priority_actions = list(dict.fromkeys(
        item["action_recommandee"] for item in [*blocking_alerts, *anomalies] if item["action_recommandee"] != "Aucune action."
    ))
    status = _overall_status(indicators)
    return {
        "formation": {"id": academic_class.programme_id, "title": str(academic_class.programme)},
        "classe": {"id": academic_class.id, "label": academic_class.display_name},
        "semestre": {"id": semester.id, "number": semester.number},
        "statut_global": _indicator(status, "Synthese pedagogique calculee.", priority_actions[0] if priority_actions else "Aucune action."),
        "indicateurs": indicators,
        "alertes_bloquantes": blocking_alerts,
        "anomalies_pedagogiques": anomalies,
        "actions_prioritaires": priority_actions,
        "timetable_state": timetable["state"],
        "read_only": True,
    }


def build_director_class_monitoring(*, actor, academic_class, week_start=None):
    require_timetable_access(actor, academic_class.branch)
    reports = [
        build_director_semester_monitoring(actor=actor, semester=semester, week_start=week_start)
        for semester in get_monitoring_semesters(academic_class=academic_class)
    ]
    return {"classe": academic_class, "semestres": reports, "read_only": True}


def build_director_monitoring_dashboard(*, actor, branch=None, programme=None, academic_year=None, week_start=None):
    if branch is not None:
        require_timetable_access(actor, branch)
    classes = get_monitoring_classes(branch=branch, programme=programme, academic_year=academic_year)
    reports = [build_director_class_monitoring(actor=actor, academic_class=row, week_start=week_start) for row in classes]
    return {
        "classes": reports,
        "global_indicators": {
            "classes": len(reports),
            "semesters": sum(len(row["semestres"]) for row in reports),
            "blocking_alerts": sum(len(report["alertes_bloquantes"]) for row in reports for report in row["semestres"]),
            "anomalies": sum(len(report["anomalies_pedagogiques"]) for row in reports for report in row["semestres"]),
        },
        "read_only": True,
    }
