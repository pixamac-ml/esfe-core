from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import PermissionDenied

from academics.models import (
    AcademicBulletin,
    AcademicCalendarEntry,
    AcademicScheduleEvent,
    EC,
    LessonLog,
    UE,
)
from academics.permissions import is_global_academic_user, user_has_branch_scope
from academics.selectors.academic_readiness_selectors import (
    get_active_ecs_for_semester,
    get_active_enrollments_for_class,
    get_active_ues_for_semester,
    get_bulletins_for_semester,
    get_calendar_entries,
    get_classes_for_programme,
    get_grades_for_semester,
    get_lesson_logs_for_class,
    get_published_calendar,
    get_schedule_events_for_class,
    get_semesters_for_class,
    get_teacher_weekly_conflicts,
    get_weekly_slots_for_class,
)


STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_BLOCKED = "blocked"

COLOR_OK = "green"
COLOR_WARNING = "amber"
COLOR_BLOCKED = "red"


def _state(status, message, action="", **extra):
    color = {
        STATUS_OK: COLOR_OK,
        STATUS_WARNING: COLOR_WARNING,
        STATUS_BLOCKED: COLOR_BLOCKED,
    }.get(status, COLOR_WARNING)
    payload = {
        "status": status,
        "color": color,
        "message": message,
        "action": action,
    }
    payload.update(extra)
    return payload


def _ok(message, action="", **extra):
    return _state(STATUS_OK, message, action, **extra)


def _warning(message, action="", **extra):
    return _state(STATUS_WARNING, message, action, **extra)


def _blocked(message, action="", **extra):
    return _state(STATUS_BLOCKED, message, action, **extra)


def _ensure_branch_access(actor, branch):
    if actor is None:
        return
    if not actor.is_authenticated:
        raise PermissionDenied("Authentification requise.")
    if is_global_academic_user(actor):
        return
    if not user_has_branch_scope(actor, branch):
        raise PermissionDenied("Acces refuse a cette annexe.")


def _merge_status(items):
    statuses = [item.get("status") for item in items if isinstance(item, dict)]
    if STATUS_BLOCKED in statuses:
        return STATUS_BLOCKED
    if STATUS_WARNING in statuses:
        return STATUS_WARNING
    return STATUS_OK


def _merge_section(label, items, ok_message, warning_message=None, blocked_message=None, action=""):
    status = _merge_status(items)
    if status == STATUS_OK:
        return _ok(ok_message, action, label=label, items=items)
    if status == STATUS_WARNING:
        return _warning(warning_message or ok_message, action, label=label, items=items)
    return _blocked(blocked_message or warning_message or ok_message, action, label=label, items=items)


def _credits_sum(ecs):
    total = Decimal("0.00")
    for ec in ecs:
        total += Decimal(str(ec.credit_required or 0))
    return total


def _programme_structure_state(semester):
    ues = list(get_active_ues_for_semester(semester))
    ecs = list(get_active_ecs_for_semester(semester))
    ue_items = []
    ec_items = []
    blocking = []

    if not ues:
        ue_items.append(_blocked("Aucune UE configuree.", "Creer les UE du semestre."))
    for ue in ues:
        ue_ecs = [ec for ec in ecs if ec.ue_id == ue.id]
        if not ue_ecs:
            item = _blocked(f"UE {ue.code} incomplete : aucun EC.", "Ajouter au moins un EC.", ue_id=ue.id)
            blocking.append(item["message"])
        elif Decimal(str(ue.credit_required or 0)) > Decimal("6.00"):
            item = _blocked(f"UE {ue.code} depasse 6 credits.", "Reequilibrer les credits EC.", ue_id=ue.id)
            blocking.append(item["message"])
        else:
            item = _ok(f"UE {ue.code} complete.", "Verifier les affectations enseignants.", ue_id=ue.id)
        ue_items.append(item)

    for ec in ecs:
        if ec.credit_required is None or ec.credit_required <= 0:
            ec_items.append(_blocked(f"EC {ec.title} sans credit valide.", "Corriger le credit EC.", ec_id=ec.id))
            blocking.append(f"EC {ec.title} sans credit valide.")
        elif ec.coefficient is None or ec.coefficient <= 0:
            ec_items.append(_blocked(f"EC {ec.title} sans coefficient valide.", "Corriger le coefficient EC.", ec_id=ec.id))
            blocking.append(f"EC {ec.title} sans coefficient valide.")
        else:
            ec_items.append(_ok(f"EC {ec.title} coherent.", "Aucune action.", ec_id=ec.id))

    configured_credits = _credits_sum(ecs)
    if configured_credits != semester.total_required_credits:
        credits = _blocked(
            f"Credits incoherents : {configured_credits} / {semester.total_required_credits}.",
            "Aligner le total des credits du semestre.",
            configured_credits=configured_credits,
            required_credits=semester.total_required_credits,
        )
    else:
        credits = _ok(
            f"Credits coherents : {configured_credits} / {semester.total_required_credits}.",
            "Aucune action.",
            configured_credits=configured_credits,
            required_credits=semester.total_required_credits,
        )

    items = [*ue_items, *ec_items, credits]
    return _merge_section(
        "programme",
        items,
        "Structure pedagogique complete.",
        "Structure pedagogique a surveiller.",
        "Structure pedagogique incomplete.",
        "Completer UE/EC/credits.",
    )


def _teachers_state(academic_class, semester):
    ecs = list(get_active_ecs_for_semester(semester))
    missing_teacher = []
    for ec in ecs:
        has_assignment = ec.director_teacher_assignments.filter(
            branch=academic_class.branch,
            academic_class=academic_class,
            is_active=True,
        ).exists()
        has_slot = ec.weekly_schedule_slots.filter(
            branch=academic_class.branch,
            academic_class=academic_class,
            academic_year=academic_class.academic_year,
            is_active=True,
        ).exists()
        if not has_assignment and not has_slot:
            missing_teacher.append(ec)

    conflicts = get_teacher_weekly_conflicts(
        branch=academic_class.branch,
        academic_year=academic_class.academic_year,
        academic_class=academic_class,
    )
    items = []
    for ec in missing_teacher:
        items.append(_blocked(f"EC sans enseignant : {ec.title}.", "Affecter un enseignant.", ec_id=ec.id))
    for conflict in conflicts:
        first = conflict["first"]
        second = conflict["second"]
        items.append(
            _blocked(
                f"Conflit enseignant : {first.teacher} sur deux creneaux incompatibles.",
                "Corriger les creneaux ou l'affectation.",
                first_slot_id=first.id,
                second_slot_id=second.id,
            )
        )
    if not items:
        items.append(_ok("Affectations enseignants coherentes.", "Aucune action."))
    return _merge_section(
        "enseignants",
        items,
        "Enseignants prets.",
        "Affectations enseignants a surveiller.",
        "Affectations enseignants incompletes.",
        "Completer les affectations pedagogiques.",
    )


def _calendar_state(academic_class, semester):
    calendar = get_published_calendar(branch=academic_class.branch, academic_year=academic_class.academic_year)
    items = []
    if calendar is None:
        items.append(_blocked("Aucun calendrier academique publie.", "Publier le calendrier academique."))
    else:
        items.append(_ok("Calendrier academique publie.", "Aucune action.", calendar_id=calendar.id))

    teaching_entries = list(
        get_calendar_entries(
            branch=academic_class.branch,
            academic_year=academic_class.academic_year,
            academic_class=academic_class,
            semester=semester,
            event_types=[
                AcademicCalendarEntry.EVENT_ACADEMIC_START,
                AcademicCalendarEntry.EVENT_SEMESTER_START,
            ],
        )
    )
    exam_entries = list(
        get_calendar_entries(
            branch=academic_class.branch,
            academic_year=academic_class.academic_year,
            academic_class=academic_class,
            semester=semester,
            event_types=[AcademicCalendarEntry.EVENT_EXAM_SESSION],
        )
    )
    retake_entries = list(
        get_calendar_entries(
            branch=academic_class.branch,
            academic_year=academic_class.academic_year,
            academic_class=academic_class,
            semester=semester,
            event_types=[AcademicCalendarEntry.EVENT_RETAKE_SESSION],
        )
    )
    exam_events = get_schedule_events_for_class(academic_class).filter(event_type=AcademicScheduleEvent.EVENT_TYPE_EXAM)

    items.append(
        _ok("Periode d'enseignement ouverte ou planifiee.", "Aucune action.")
        if teaching_entries
        else _blocked("Aucune periode d'enseignement publiee.", "Publier une periode d'enseignement.")
    )
    items.append(
        _ok("Examens planifies.", "Aucune action.")
        if exam_entries or exam_events.exists()
        else _blocked("Aucun examen planifie.", "Planifier la session d'examen.")
    )
    items.append(
        _ok("Rattrapages planifies.", "Aucune action.")
        if retake_entries
        else _warning("Aucune session de rattrapage publiee.", "Planifier si applicable.")
    )

    return _merge_section(
        "calendrier",
        items,
        "Calendrier pret.",
        "Calendrier partiellement pret.",
        "Calendrier incomplet.",
        "Publier les jalons academiques.",
    )


def _timetable_state(academic_class, semester):
    slots = list(get_weekly_slots_for_class(academic_class))
    ecs = list(get_active_ecs_for_semester(semester))
    items = []
    if not slots:
        items.append(_blocked("Aucun emploi du temps pour cette classe.", "Creer les creneaux hebdomadaires."))
    else:
        items.append(_ok("Emploi du temps present.", "Verifier les conflits."))

    scheduled_ec_ids = {slot.ec_id for slot in slots}
    missing_ecs = [ec for ec in ecs if ec.id not in scheduled_ec_ids]
    for ec in missing_ecs:
        items.append(_blocked(f"EC sans creneau : {ec.title}.", "Ajouter un creneau.", ec_id=ec.id))

    conflicts = get_teacher_weekly_conflicts(
        branch=academic_class.branch,
        academic_year=academic_class.academic_year,
        academic_class=academic_class,
    )
    for conflict in conflicts:
        items.append(
            _blocked(
                f"Conflit d'emploi du temps detecte pour {conflict['first'].teacher}.",
                "Corriger le planning.",
            )
        )

    return _merge_section(
        "emploi_du_temps",
        items,
        "Emploi du temps pret.",
        "Emploi du temps a surveiller.",
        "Emploi du temps incomplet.",
        "Completer les creneaux manquants.",
    )


def _pedagogical_followup_state(academic_class):
    logs = get_lesson_logs_for_class(academic_class)
    items = []
    if not logs.exists():
        items.append(_warning("Aucun cahier de texte ouvert.", "Demarrer le suivi pedagogique."))
    else:
        items.append(_ok("Cahiers de texte ouverts.", "Suivre les seances non realisees."))

    not_done = logs.filter(status__in=[LessonLog.STATUS_PLANNED, LessonLog.STATUS_ABSENT_TEACHER]).count()
    cancelled = logs.filter(status=LessonLog.STATUS_CANCELLED).count()
    if not_done:
        items.append(_warning(f"{not_done} seance(s) non realisee(s).", "Relancer les enseignants."))
    if cancelled:
        items.append(_warning(f"{cancelled} seance(s) annulee(s).", "Verifier le rattrapage des seances."))
    if len(items) == 1 and items[0]["status"] == STATUS_OK:
        items.append(_ok("Aucun retard pedagogique detecte.", "Aucune action."))

    return _merge_section(
        "suivi_pedagogique",
        items,
        "Suivi pedagogique pret.",
        "Suivi pedagogique a surveiller.",
        "Suivi pedagogique bloque.",
        "Verifier les cahiers de texte.",
    )


def _notes_state(academic_class, semester):
    enrollments = list(get_active_enrollments_for_class(academic_class))
    ecs = list(get_active_ecs_for_semester(semester))
    grades = list(get_grades_for_semester(semester))
    grades_by_pair = {(grade.enrollment_id, grade.ec_id): grade for grade in grades}
    items = []

    if not enrollments:
        items.append(_warning("Aucune inscription active dans cette classe.", "Verifier les affectations etudiants."))
    if not ecs:
        items.append(_blocked("Aucun EC : impossible de verifier les notes.", "Completer la structure pedagogique."))
    if enrollments and ecs and not grades:
        items.append(_blocked("Notes non importees.", "Importer les notes via le dashboard Informaticien."))

    missing_scores = 0
    unvalidated = 0
    for enrollment in enrollments:
        for ec in ecs:
            grade = grades_by_pair.get((enrollment.id, ec.id))
            if grade is None or grade.final_score is None:
                missing_scores += 1
            elif not grade.is_validated:
                unvalidated += 1

    if missing_scores:
        items.append(_blocked(f"{missing_scores} note(s) manquante(s).", "Completer l'import des notes."))
    if unvalidated:
        items.append(_blocked(f"{unvalidated} note(s) non validee(s) par l'informaticien.", "Demander validation IT."))
    if not items:
        items.append(_ok("Notes importees, completes et validees.", "Aucune action."))

    bulletins = get_bulletins_for_semester(semester)
    provisional_count = bulletins.filter(status__in=[AcademicBulletin.STATUS_DRAFT, AcademicBulletin.STATUS_GENERATED]).count()
    if enrollments and provisional_count < len(enrollments):
        items.append(_warning("Bulletins provisoires incomplets.", "Generer les bulletins provisoires."))
    elif enrollments:
        items.append(_ok("Bulletins provisoires disponibles.", "Verifier avant publication."))

    return _merge_section(
        "notes",
        items,
        "Notes pretes.",
        "Notes ou bulletins provisoires a surveiller.",
        "Notes incompletes.",
        "Passer par le dashboard Informaticien.",
    )


def build_semester_readiness(*, actor=None, semester):
    academic_class = semester.academic_class
    _ensure_branch_access(actor, academic_class.branch)

    programme = _programme_structure_state(semester)
    teachers = _teachers_state(academic_class, semester)
    calendar = _calendar_state(academic_class, semester)
    timetable = _timetable_state(academic_class, semester)
    followup = _pedagogical_followup_state(academic_class)
    notes = _notes_state(academic_class, semester)
    sections = [programme, teachers, calendar, timetable, followup, notes]
    blocking = [
        item["message"]
        for section in sections
        for item in section.get("items", [])
        if item.get("status") == STATUS_BLOCKED
    ]
    can_publish = not blocking

    return {
        "formation": {
            "id": academic_class.programme_id,
            "title": str(academic_class.programme),
        },
        "classe": {
            "id": academic_class.id,
            "label": academic_class.display_name,
            "branch_id": academic_class.branch_id,
            "academic_year_id": academic_class.academic_year_id,
        },
        "semestre": {
            "id": semester.id,
            "number": semester.number,
            "status": semester.status,
        },
        "etat_general": _merge_section(
            "etat_general",
            sections,
            "Classe prete pour publication.",
            "Classe partiellement prete.",
            "Classe non prete pour publication.",
            "Traiter les anomalies bloquantes.",
        ),
        "programme": programme,
        "enseignants": teachers,
        "calendrier": calendar,
        "emploi_du_temps": timetable,
        "suivi_pedagogique": followup,
        "examens": calendar,
        "notes": notes,
        "bulletins": {
            "status": notes["status"],
            "color": notes["color"],
            "message": "Voir section notes/bulletins provisoires.",
            "action": "Generer ou verifier les bulletins provisoires.",
        },
        "validation": {
            "can_publish": can_publish,
            "answer": "OUI" if can_publish else "NON",
            "status": STATUS_OK if can_publish else STATUS_BLOCKED,
            "color": COLOR_OK if can_publish else COLOR_BLOCKED,
            "message": "Publication autorisee." if can_publish else "Publication impossible.",
            "action": "Publier." if can_publish else "Corriger les anomalies bloquantes.",
            "blocking_anomalies": blocking,
        },
    }


def build_class_readiness(*, actor=None, academic_class):
    _ensure_branch_access(actor, academic_class.branch)
    semesters = list(get_semesters_for_class(academic_class))
    semester_reports = [build_semester_readiness(actor=actor, semester=semester) for semester in semesters]
    blocking = [
        anomaly
        for report in semester_reports
        for anomaly in report["validation"]["blocking_anomalies"]
    ]
    return {
        "formation": {"id": academic_class.programme_id, "title": str(academic_class.programme)},
        "classe": {"id": academic_class.id, "label": academic_class.display_name},
        "semestres": semester_reports,
        "validation": {
            "can_publish": not blocking and bool(semester_reports),
            "answer": "OUI" if not blocking and semester_reports else "NON",
            "status": STATUS_OK if not blocking and semester_reports else STATUS_BLOCKED,
            "color": COLOR_OK if not blocking and semester_reports else COLOR_BLOCKED,
            "message": "Classe prete." if not blocking and semester_reports else "Classe non prete.",
            "action": "Publier." if not blocking and semester_reports else "Traiter les anomalies.",
            "blocking_anomalies": blocking or ([] if semester_reports else ["Aucun semestre configure."]),
        },
    }


def build_programme_readiness(*, actor=None, programme, branch=None, academic_year=None):
    classes = list(get_classes_for_programme(programme=programme, branch=branch, academic_year=academic_year))
    if actor is not None and not is_global_academic_user(actor):
        classes = [academic_class for academic_class in classes if user_has_branch_scope(actor, academic_class.branch)]
    if actor is not None and not classes and branch is not None:
        _ensure_branch_access(actor, branch)

    class_reports = [build_class_readiness(actor=actor, academic_class=academic_class) for academic_class in classes]
    blocking = [
        anomaly
        for report in class_reports
        for anomaly in report["validation"]["blocking_anomalies"]
    ]
    can_publish = bool(class_reports) and not blocking
    return {
        "formation": {"id": programme.id, "title": str(programme)},
        "classes": class_reports,
        "validation": {
            "can_publish": can_publish,
            "answer": "OUI" if can_publish else "NON",
            "status": STATUS_OK if can_publish else STATUS_BLOCKED,
            "color": COLOR_OK if can_publish else COLOR_BLOCKED,
            "message": "Programme pret." if can_publish else "Programme non pret.",
            "action": "Publier." if can_publish else "Traiter les anomalies.",
            "blocking_anomalies": blocking or ([] if class_reports else ["Aucune classe trouvee."]),
        },
    }
