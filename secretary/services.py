from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from accounts.dashboards.helpers import get_user_branch
from communication.models import CommunicationNotification
from communication.services.notification_service import NotificationService
from academics.services.schedule_service import get_student_week_schedule
from students.models import StudentAttendance
from .models import Appointment, DocumentReceipt, RegistryEntry, SecretaryTask, VisitorLog
from .selectors import (
    get_active_students,
    get_active_visits_queryset,
    get_documents_queryset,
    get_recent_documents_queryset,
    get_recent_registry_entries,
    get_registry_queryset,
    get_classes_queryset,
    get_class_students_queryset,
    get_tasks_queryset,
    search_classes,
    get_student_active_enrollment,
    get_student_snapshot_queryset,
    get_today_appointments_queryset,
    get_today_visits_queryset,
    get_secretary_notifications as selector_notifications,
    get_unread_messages_count,
    get_user_messages,
    search_students as search_students_queryset,
)


User = get_user_model()


def _clean_instance(instance):
    instance.full_clean()
    instance.save()
    return instance


def _notify_recipient(*, recipient, actor, event_type, title, body, metadata, legacy_source, legacy_object_id):
    NotificationService.notify_user(
        recipient=recipient,
        actor=actor,
        event_type=event_type,
        title=title,
        body=body,
        source_app="secretary",
        channels=(CommunicationNotification.CHANNEL_IN_APP, CommunicationNotification.CHANNEL_WEBSOCKET),
        metadata=metadata,
        legacy_source=legacy_source,
        legacy_object_id=legacy_object_id,
    )


REGISTRY_ROUTING_RULES = {
    RegistryEntry.TYPE_SCHOOL_PAYMENT: {
        "target_service": "Gestionnaire",
        "priority": RegistryEntry.PRIORITY_IMMEDIATE,
        "workflow_code": "financial",
        "actions": ["Notifier la gestionnaire", "Ouvrir le dossier financier", "Preparer le recu"],
    },
    RegistryEntry.TYPE_PACKAGE_DEPOSIT: {
        "target_service": "Surveillance",
        "priority": RegistryEntry.PRIORITY_HIGH,
        "workflow_code": "package_delivery",
        "actions": ["Identifier l'etudiant", "Notifier surveillant/etudiant", "Confirmer la remise"],
    },
    RegistryEntry.TYPE_SCHOOL_DELIVERY: {
        "target_service": "Gestionnaire / Logistique",
        "priority": RegistryEntry.PRIORITY_HIGH,
        "workflow_code": "logistics",
        "actions": ["Verifier livraison", "Notifier logistique", "Archiver justificatif"],
    },
    RegistryEntry.TYPE_APPOINTMENT_REQUEST: {
        "target_service": "Secretariat direction",
        "priority": RegistryEntry.PRIORITY_NORMAL,
        "workflow_code": "appointment",
        "actions": ["Consulter agenda", "Valider creneau", "Envoyer confirmation"],
    },
    RegistryEntry.TYPE_DIPLOMA_WITHDRAWAL: {
        "target_service": "Direction des etudes",
        "priority": RegistryEntry.PRIORITY_HIGH,
        "workflow_code": "diploma_withdrawal",
        "actions": ["Verifier identite", "Verifier disponibilite", "Archiver signature"],
    },
    RegistryEntry.TYPE_COMPLAINT: {
        "target_service": "Administration",
        "priority": RegistryEntry.PRIORITY_HIGH,
        "workflow_code": "complaint",
        "actions": ["Qualifier reclamation", "Router service", "Suivre resolution"],
    },
    RegistryEntry.TYPE_EXTERNAL_VISITOR: {
        "target_service": "Accueil / Administration",
        "priority": RegistryEntry.PRIORITY_NORMAL,
        "workflow_code": "external_visit",
        "actions": ["Identifier visiteur", "Orienter service", "Tracer sortie"],
    },
    RegistryEntry.TYPE_PARENT_VISIT: {
        "target_service": "Accueil / Pedagogie",
        "priority": RegistryEntry.PRIORITY_NORMAL,
        "workflow_code": "parent_visit",
        "actions": ["Identifier enfant", "Orienter interlocuteur", "Tracer echange"],
    },
}


# Positions du personnel a notifier lorsqu'une entree de registre est routee
# vers un service cible (voir REGISTRY_ROUTING_RULES). Cle = entry_type.
ROUTING_NOTIFICATION_POSITIONS = {
    RegistryEntry.TYPE_SCHOOL_PAYMENT: ("branch_manager",),
    RegistryEntry.TYPE_PACKAGE_DEPOSIT: ("academic_supervisor",),
    RegistryEntry.TYPE_SCHOOL_DELIVERY: ("branch_manager",),
    RegistryEntry.TYPE_APPOINTMENT_REQUEST: ("director_of_studies",),
    RegistryEntry.TYPE_DIPLOMA_WITHDRAWAL: ("director_of_studies",),
    RegistryEntry.TYPE_COMPLAINT: ("branch_manager",),
    RegistryEntry.TYPE_EXTERNAL_VISITOR: ("branch_manager",),
    RegistryEntry.TYPE_PARENT_VISIT: ("director_of_studies",),
}


def _notify_registry_routing(entry, *, actor, event_type, title, body):
    positions = ROUTING_NOTIFICATION_POSITIONS.get(entry.entry_type)
    if not positions or not entry.branch_id:
        return
    rule = REGISTRY_ROUTING_RULES.get(entry.entry_type, {})
    recipients = User.objects.filter(
        profile__position__in=positions, profile__branch_id=entry.branch_id
    ).exclude(pk=getattr(actor, "pk", None)).distinct()
    for recipient in recipients:
        _notify_recipient(
            recipient=recipient,
            actor=actor,
            event_type=event_type,
            title=title,
            body=body,
            metadata={
                "registry_entry_id": entry.pk,
                "target_service": rule.get("target_service", "Accueil"),
            },
            legacy_source="secretary_registry",
            legacy_object_id=str(entry.pk),
        )


def get_registry_routing_rules_for_ui():
    choices = dict(RegistryEntry.ENTRY_TYPE_CHOICES)
    priorities = dict(RegistryEntry.PRIORITY_CHOICES)
    return {
        entry_type: {
            "label": choices.get(entry_type, entry_type),
            "target_service": rule.get("target_service", "Accueil"),
            "priority": rule.get("priority", RegistryEntry.PRIORITY_NORMAL),
            "priority_label": priorities.get(rule.get("priority", RegistryEntry.PRIORITY_NORMAL), "Normale"),
            "workflow_code": rule.get("workflow_code", "administrative"),
            "actions": rule.get("actions", []),
        }
        for entry_type, rule in REGISTRY_ROUTING_RULES.items()
    }


def apply_registry_routing(data):
    entry_type = data.get("entry_type")
    rule = REGISTRY_ROUTING_RULES.get(entry_type, {})
    if not data.get("target_service"):
        data["target_service"] = rule.get("target_service", "Accueil")
    data["priority"] = rule.get("priority", data.get("priority") or RegistryEntry.PRIORITY_NORMAL)
    if not data.get("workflow_code"):
        data["workflow_code"] = rule.get("workflow_code", "administrative")
    if not data.get("linked_actions"):
        data["linked_actions"] = rule.get("actions", [])
    return data


def _next_registry_numbers(*, branch):
    today = timezone.localdate()
    year = today.year
    branch_code = (getattr(branch, "code", "") or "GLOBAL").upper()
    branch_filter = {"branch": branch} if branch else {"branch__isnull": True}
    day_sequence = (
        RegistryEntry.objects.filter(created_at__date=today, **branch_filter).count() + 1
    )
    year_sequence = (
        RegistryEntry.objects.filter(created_at__year=year, **branch_filter).count() + 1
    )
    registry_number = f"ESFE-{branch_code}-{year}-{year_sequence:06d}"
    event_identifier = f"{registry_number}-{day_sequence:03d}"
    return registry_number, day_sequence, event_identifier


def _history_event(user, action, details=None):
    return {
        "at": timezone.now().isoformat(),
        "by": getattr(user, "username", "") if user else "",
        "action": action,
        "details": details or {},
    }


def prevent_conflicts(*, scheduled_at, assigned_to=None, exclude_id=None):
    if scheduled_at < timezone.now():
        raise ValidationError("Un rendez-vous ne peut pas etre planifie dans le passe.")

    queryset = Appointment.objects.filter(scheduled_at=scheduled_at, is_archived=False)
    if exclude_id:
        queryset = queryset.exclude(id=exclude_id)

    if assigned_to and queryset.filter(assigned_to=assigned_to).exists():
        raise ValidationError("Un autre rendez-vous est deja planifie pour cet agent a ce meme horaire.")

    return True


@transaction.atomic
def create_registry_entry(*, created_by, **data):
    branch = data.get("branch") or get_user_branch(created_by)
    data["branch"] = branch
    data = apply_registry_routing(data)
    if not data.get("title"):
        entry_type_labels = dict(RegistryEntry.ENTRY_TYPE_CHOICES)
        visitor = data.get("visitor_name") or "Accueil"
        data["title"] = f"{entry_type_labels.get(data.get('entry_type'), 'Entree registre')} - {visitor}"
    if not data.get("registry_number"):
        registry_number, daily_number, event_identifier = _next_registry_numbers(branch=branch)
        data["registry_number"] = registry_number
        data["daily_number"] = daily_number
        data["event_identifier"] = event_identifier
    data["history"] = [_history_event(created_by, "creation", {"entry_type": data.get("entry_type")})]
    entry = RegistryEntry(created_by=created_by, **data)
    entry = _clean_instance(entry)
    rule = REGISTRY_ROUTING_RULES.get(entry.entry_type, {})
    _notify_registry_routing(
        entry,
        actor=created_by,
        event_type="secretary_registry_routed",
        title=f"Registre route vers {rule.get('target_service', 'Accueil')}",
        body=entry.title,
    )
    return entry


@transaction.atomic
def start_registry_entry_processing(entry):
    if entry.is_archived:
        raise ValidationError("Une entree archivee ne peut pas etre reprise.")
    if entry.status == RegistryEntry.STATUS_PENDING:
        entry.status = RegistryEntry.STATUS_IN_PROGRESS
    elif entry.status == RegistryEntry.STATUS_COMPLETED:
        raise ValidationError("Cette entree a deja ete traitee.")
    entry.history.append(_history_event(None, "prise_en_charge"))
    return _clean_instance(entry)


@transaction.atomic
def update_registry_entry(entry, **data):
    data = apply_registry_routing(data)
    new_status = data.get("status")
    previous_status = entry.status
    entry.validate_status_transition(new_status)
    for field, value in data.items():
        setattr(entry, field, value)
    if new_status and new_status != previous_status:
        entry.history.append(_history_event(None, "changement_statut", {
            "from": previous_status,
            "to": new_status,
        }))
    entry.history.append(_history_event(None, "mise_a_jour"))
    return _clean_instance(entry)


@transaction.atomic
def move_registry_entry_status(entry, new_status):
    if entry.is_archived:
        raise ValidationError("Une entree archivee ne peut pas etre deplacee.")
    entry.validate_status_transition(new_status)
    previous_status = entry.status
    if new_status == previous_status:
        return entry
    entry.status = new_status
    if new_status == RegistryEntry.STATUS_COMPLETED and not entry.closed_at:
        entry.closed_at = timezone.now()
    entry.history.append(_history_event(None, "changement_statut", {
        "from": previous_status,
        "to": new_status,
    }))
    return _clean_instance(entry)


@transaction.atomic
def mark_registry_processed(entry):
    if entry.is_archived:
        raise ValidationError("Une entree archivee ne peut pas etre validee.")
    entry.status = RegistryEntry.STATUS_COMPLETED
    entry.closed_at = timezone.now()
    entry.history.append(_history_event(None, "traite"))
    return _clean_instance(entry)


@transaction.atomic
def archive_registry_entry(entry):
    if entry.is_archived:
        raise ValidationError("Cette entree est deja archivee.")
    entry.is_archived = True
    entry.is_active = False
    entry.status = RegistryEntry.STATUS_ARCHIVED
    entry.history.append(_history_event(None, "archive"))
    return _clean_instance(entry)


@transaction.atomic
def register_visitor(*, created_by, **data):
    visitor = VisitorLog(created_by=created_by, **data)
    if not visitor.status:
        visitor.status = VisitorLog.STATUS_IN_PROGRESS
    return _clean_instance(visitor)


@transaction.atomic
def update_visitor(visitor, **data):
    for field, value in data.items():
        setattr(visitor, field, value)
    return _clean_instance(visitor)


@transaction.atomic
def close_visit(visitor, departed_at=None):
    if visitor.is_archived:
        raise ValidationError("Une visite archivee ne peut pas etre cloturee.")
    if visitor.departed_at:
        raise ValidationError("Cette visite est deja cloturee.")

    visitor.departed_at = departed_at or timezone.now()
    visitor.status = VisitorLog.STATUS_COMPLETED
    return _clean_instance(visitor)


def get_active_visits(*, user=None, branch=None):
    return get_active_visits_queryset(user=user, branch=branch)


def get_today_visits(*, user=None, branch=None):
    return get_today_visits_queryset(user=user, branch=branch)


@transaction.atomic
def create_appointment(*, created_by, **data):
    scheduled_at = data.get("scheduled_at")
    assigned_to = data.get("assigned_to")
    prevent_conflicts(scheduled_at=scheduled_at, assigned_to=assigned_to)
    appointment = Appointment(created_by=created_by, **data)
    appointment = _clean_instance(appointment)
    if appointment.assigned_to_id and appointment.assigned_to_id != created_by.id:
        _notify_recipient(
            recipient=appointment.assigned_to,
            actor=created_by,
            event_type="secretary_appointment_assigned",
            title="Nouveau rendez-vous assigne",
            body=f"{appointment.title} - {appointment.scheduled_at:%d/%m/%Y %H:%M}",
            metadata={"appointment_id": appointment.pk},
            legacy_source="secretary_appointment",
            legacy_object_id=str(appointment.pk),
        )
    return appointment


@transaction.atomic
def validate_appointment(appointment):
    return start_appointment_processing(appointment)


@transaction.atomic
def start_appointment_processing(appointment):
    if appointment.is_archived:
        raise ValidationError("Un rendez-vous archive ne peut pas etre repris.")
    if appointment.status == Appointment.STATUS_COMPLETED:
        raise ValidationError("Ce rendez-vous est deja termine.")
    appointment.status = Appointment.STATUS_IN_PROGRESS
    return _clean_instance(appointment)


def get_upcoming_appointments():
    return Appointment.objects.select_related(
        "assigned_to",
        "related_student__user",
    ).filter(
        scheduled_at__gte=timezone.now(),
        is_archived=False,
        is_active=True,
    ).order_by("scheduled_at")


def get_today_appointments(*, user=None, branch=None):
    return get_today_appointments_queryset(user=user, branch=branch)


@transaction.atomic
def update_appointment(appointment, actor=None, **data):
    scheduled_at = data.get("scheduled_at", appointment.scheduled_at)
    assigned_to = data.get("assigned_to", appointment.assigned_to)
    prevent_conflicts(scheduled_at=scheduled_at, assigned_to=assigned_to, exclude_id=appointment.pk)
    previous_assigned_to_id = appointment.assigned_to_id
    for field, value in data.items():
        setattr(appointment, field, value)
    appointment = _clean_instance(appointment)
    if (
        appointment.assigned_to_id
        and appointment.assigned_to_id != previous_assigned_to_id
        and (actor is None or appointment.assigned_to_id != actor.id)
    ):
        _notify_recipient(
            recipient=appointment.assigned_to,
            actor=actor,
            event_type="secretary_appointment_assigned",
            title="Rendez-vous assigne",
            body=f"{appointment.title} - {appointment.scheduled_at:%d/%m/%Y %H:%M}",
            metadata={"appointment_id": appointment.pk},
            legacy_source="secretary_appointment",
            legacy_object_id=str(appointment.pk),
        )
    return appointment


@transaction.atomic
def complete_appointment(appointment):
    if appointment.is_archived:
        raise ValidationError("Un rendez-vous archive ne peut pas etre complete.")
    if appointment.status == Appointment.STATUS_COMPLETED:
        raise ValidationError("Ce rendez-vous est deja termine.")
    appointment.status = Appointment.STATUS_COMPLETED
    return _clean_instance(appointment)


@transaction.atomic
def archive_appointment(appointment):
    if appointment.is_archived:
        raise ValidationError("Ce rendez-vous est deja archive.")
    appointment.is_archived = True
    appointment.is_active = False
    appointment.status = Appointment.STATUS_ARCHIVED
    return _clean_instance(appointment)


@transaction.atomic
def register_document(*, received_by, **data):
    document = DocumentReceipt(received_by=received_by, **data)
    document = _clean_instance(document)
    if document.related_registry_id:
        _notify_registry_routing(
            document.related_registry,
            actor=received_by,
            event_type="secretary_document_deposited",
            title="Document depose pour une entree routee",
            body=document.title,
        )
    return document


@transaction.atomic
def start_document_processing(document):
    if document.is_archived:
        raise ValidationError("Un document archive ne peut pas etre repris.")
    if document.status == DocumentReceipt.STATUS_PENDING:
        document.status = DocumentReceipt.STATUS_IN_PROGRESS
    elif document.status == DocumentReceipt.STATUS_COMPLETED:
        raise ValidationError("Ce document a deja ete traite.")
    return _clean_instance(document)


@transaction.atomic
def update_document(document, **data):
    for field, value in data.items():
        setattr(document, field, value)
    return _clean_instance(document)


@transaction.atomic
def archive_document(document):
    if document.is_archived:
        raise ValidationError("Ce document est deja archive.")
    document.is_archived = True
    document.is_active = False
    if document.status == DocumentReceipt.STATUS_IN_PROGRESS:
        document.status = DocumentReceipt.STATUS_COMPLETED
    return _clean_instance(document)



def get_recent_documents(limit=5, *, user=None, branch=None):
    return get_recent_documents_queryset(limit=limit, user=user, branch=branch)


@transaction.atomic
def create_task(*, created_by, **data):
    task = SecretaryTask(created_by=created_by, **data)
    task = _clean_instance(task)
    if task.assigned_to_id and task.assigned_to_id != created_by.id:
        _notify_recipient(
            recipient=task.assigned_to,
            actor=created_by,
            event_type="secretary_task_assigned",
            title="Nouvelle tache assignee",
            body=task.title,
            metadata={"task_id": task.pk},
            legacy_source="secretary_task",
            legacy_object_id=str(task.pk),
        )
    return task


@transaction.atomic
def start_task_processing(task, user):
    assign_task(task, user)
    if task.status == SecretaryTask.STATUS_PENDING:
        task.status = SecretaryTask.STATUS_IN_PROGRESS
    return _clean_instance(task)


@transaction.atomic
def assign_task(task, user):
    if task.is_archived:
        raise ValidationError("Une tache archivee ne peut pas etre reprise.")
    task.assigned_to = user
    if task.status == SecretaryTask.STATUS_PENDING:
        task.status = SecretaryTask.STATUS_IN_PROGRESS
    return _clean_instance(task)


@transaction.atomic
def update_task(task, actor=None, **data):
    previous_assigned_to_id = task.assigned_to_id
    for field, value in data.items():
        setattr(task, field, value)
    task = _clean_instance(task)
    if (
        task.assigned_to_id
        and task.assigned_to_id != previous_assigned_to_id
        and (actor is None or task.assigned_to_id != actor.id)
    ):
        _notify_recipient(
            recipient=task.assigned_to,
            actor=actor,
            event_type="secretary_task_assigned",
            title="Tache assignee",
            body=task.title,
            metadata={"task_id": task.pk},
            legacy_source="secretary_task",
            legacy_object_id=str(task.pk),
        )
    return task


@transaction.atomic
def complete_task(task):
    if task.is_archived:
        raise ValidationError("Une tache archivee ne peut pas etre terminee.")
    if task.status == SecretaryTask.STATUS_COMPLETED:
        raise ValidationError("Cette tache est deja terminee.")
    task.status = SecretaryTask.STATUS_COMPLETED
    return _clean_instance(task)


def get_pending_tasks(*, user=None, branch=None):
    return get_tasks_queryset(
        {
            "archived": False,
            "active_only": True,
        },
        user=user,
        branch=branch,
    ).filter(
        status__in=[SecretaryTask.STATUS_PENDING, SecretaryTask.STATUS_IN_PROGRESS],
    )


def search_students(query, *, user=None, branch=None):
    return search_students_queryset(query, user=user, branch=branch)


def search_academic_classes(query, *, user=None, branch=None):
    return search_classes(query, user=user, branch=branch)


def get_secretary_classes(*, user=None, branch=None, limit=24):
    return get_classes_queryset(user=user, branch=branch)[:limit]


def get_secretary_class_students(academic_class_id, *, user=None, branch=None):
    return get_class_students_queryset(academic_class_id, user=user, branch=branch)


def get_student_snapshot(student_id, *, user=None, branch=None):
    student = get_object_or_404(get_student_snapshot_queryset(student_id, user=user, branch=branch))
    enrollment = get_student_active_enrollment(student)
    inscription = getattr(student, "inscription", None)
    candidature = getattr(inscription, "candidature", None)
    schedule = _get_secretary_student_schedule(student)
    return {
        "student_id": student.id,
        "full_name": student.full_name,
        "matricule": student.matricule,
        "email": student.email,
        "programme": getattr(getattr(candidature, "programme", None), "title", ""),
        "branch": getattr(getattr(candidature, "branch", None), "name", ""),
        "academic_class": str(getattr(enrollment, "academic_class", "") or ""),
        "academic_year": str(getattr(enrollment, "academic_year", "") or ""),
        "registry_entries_count": student.registry_entries.filter(is_archived=False).count(),
        "appointments_count": student.appointments.filter(is_archived=False).count(),
        "open_visits_count": student.visitor_logs.filter(
            status=VisitorLog.STATUS_IN_PROGRESS,
            is_archived=False,
        ).count(),
        "documents_count": student.document_receipts.filter(is_archived=False).count(),
        "tasks_count": student.secretary_tasks.filter(is_archived=False).count(),
        "schedule": schedule,
        "today_events": schedule.get("today_events", []),
        "current_event": schedule.get("current_event"),
        "presence_state": schedule.get("presence_state", {}),
    }


def _get_secretary_student_schedule(student):
    schedule = get_student_week_schedule(student, None)
    today = timezone.localdate()
    now = timezone.localtime(timezone.now())
    events = list(schedule.get("events", []))
    event_ids = [event["id"] for event in events if isinstance(event.get("id"), int)]
    attendances = {
        attendance.schedule_event_id: attendance
        for attendance in StudentAttendance.objects.filter(
            student=student,
            date=today,
            schedule_event_id__in=event_ids,
        ).select_related("schedule_event")
    }

    current_event = None
    today_events = []
    for event in events:
        duration_minutes = event.get("duration_minutes") or 0
        event["duration_label"] = f"{duration_minutes} min" if duration_minutes else ""
        attendance = attendances.get(event.get("id"))
        event["attendance_status"] = getattr(attendance, "status", "")
        event["attendance_label"] = attendance.get_status_display() if attendance else "Non pointe"
        event["attendance_is_recorded"] = attendance is not None
        if event.get("is_today"):
            today_events.append(event)
            start_dt = timezone.localtime(event["start_datetime"])
            end_dt = timezone.localtime(event["end_datetime"])
            if start_dt <= now <= end_dt and not event.get("is_cancelled"):
                current_event = event

    for day_index, day in enumerate(schedule.get("days", [])):
        day_events = [
            event for event in events
            if event.get("weekday_index") == day_index
        ]
        day["events"] = day_events
        day["events_count"] = len(day_events)

    schedule["today_events"] = today_events
    schedule["today_events_count"] = len(today_events)
    schedule["current_event"] = current_event
    schedule["week_end"] = schedule["days"][-1]["date"] if schedule.get("days") else schedule.get("week_start")
    schedule["presence_state"] = {
        "has_course_now": current_event is not None,
        "label": _student_presence_label(current_event),
        "tone": _student_presence_tone(current_event),
    }
    return schedule


def _student_presence_label(current_event):
    if current_event is None:
        return "Pas de cours en ce moment"
    status = current_event.get("attendance_status")
    if status == StudentAttendance.STATUS_PRESENT:
        return "Declare present au cours"
    if status == StudentAttendance.STATUS_LATE:
        return "Declare en retard au cours"
    if status == StudentAttendance.STATUS_ABSENT:
        return "Declare absent au cours"
    return "Cours en cours - presence non pointee"


def _student_presence_tone(current_event):
    if current_event is None:
        return "slate"
    status = current_event.get("attendance_status")
    if status == StudentAttendance.STATUS_PRESENT:
        return "green"
    if status == StudentAttendance.STATUS_LATE:
        return "amber"
    if status == StudentAttendance.STATUS_ABSENT:
        return "red"
    return "blue"


def get_secretary_dashboard_data(user):
    branch = get_user_branch(user)
    active_students = get_active_students(user=user, branch=branch)
    today_appointments = get_today_appointments(user=user, branch=branch)
    today_visits = get_today_visits(user=user, branch=branch)
    active_visits = get_active_visits(user=user, branch=branch)
    pending_tasks = get_pending_tasks(user=user, branch=branch)
    classes_queryset = get_classes_queryset(user=user, branch=branch)
    classes = classes_queryset[:24]
    pending_registry_rows = get_registry_queryset(
        {
            "status": RegistryEntry.STATUS_PENDING,
            "archived": False,
            "active_only": True,
        },
        user=user,
        branch=branch,
    )[:5]
    pending_documents_rows = get_documents_queryset(
        {
            "status": DocumentReceipt.STATUS_PENDING,
            "archived": False,
            "active_only": True,
        },
        user=user,
        branch=branch,
    )[:5]

    return {
        "branch": branch,
        "students_count": active_students.count(),
        "students_preview_rows": active_students[:12],
        "classes_count": classes_queryset.count(),
        "classes_rows": classes,
        "appointments_today": today_appointments.count(),
        "visits_today": today_visits.count(),
        "active_visits": active_visits.count(),
        "pending_tasks": pending_tasks.count(),
        "pending_registry_count": get_registry_queryset(
            {
                "status": RegistryEntry.STATUS_PENDING,
                "archived": False,
                "active_only": True,
            },
            user=user,
            branch=branch,
        ).count(),
        "pending_documents_count": get_documents_queryset(
            {
                "status": DocumentReceipt.STATUS_PENDING,
                "archived": False,
                "active_only": True,
            },
            user=user,
            branch=branch,
        ).count(),
        "today_appointments_rows": today_appointments[:5],
        "today_visits_rows": today_visits[:5],
        "open_visits_rows": active_visits[:5],
        "pending_tasks_rows": pending_tasks[:5],
        "pending_registry_rows": pending_registry_rows,
        "pending_documents_rows": pending_documents_rows,
        "recent_registry": get_recent_registry_entries(limit=5, user=user, branch=branch),
        "recent_documents": get_recent_documents(limit=5, user=user, branch=branch),
        "messages_count": get_secretary_unread_messages(user),
        "recent_messages": get_secretary_recent_messages(user, limit=5),
        "notifications": get_secretary_notifications(user, limit=5),
    }


def get_secretary_unread_messages(user):
    return get_unread_messages_count(user)


def get_secretary_recent_messages(user, limit=10):
    return get_user_messages(user, limit=limit)


def get_secretary_notifications(user, limit=10):
    return selector_notifications(user, limit=limit)
