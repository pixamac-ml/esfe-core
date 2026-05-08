from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from accounts.dashboards.helpers import get_user_branch
from .models import Appointment, DocumentReceipt, RegistryEntry, SecretaryTask, VisitorLog
from .selectors import (
    get_active_students,
    get_active_visits_queryset,
    get_documents_queryset,
    get_recent_documents_queryset,
    get_recent_registry_entries,
    get_registry_queryset,
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


def _clean_instance(instance):
    instance.full_clean()
    instance.save()
    return instance


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
    entry = RegistryEntry(created_by=created_by, **data)
    return _clean_instance(entry)


@transaction.atomic
def start_registry_entry_processing(entry):
    if entry.is_archived:
        raise ValidationError("Une entree archivee ne peut pas etre reprise.")
    if entry.status == RegistryEntry.STATUS_PENDING:
        entry.status = RegistryEntry.STATUS_IN_PROGRESS
    elif entry.status == RegistryEntry.STATUS_COMPLETED:
        raise ValidationError("Cette entree a deja ete traitee.")
    return _clean_instance(entry)


@transaction.atomic
def update_registry_entry(entry, **data):
    for field, value in data.items():
        setattr(entry, field, value)
    return _clean_instance(entry)


@transaction.atomic
def mark_registry_processed(entry):
    if entry.is_archived:
        raise ValidationError("Une entree archivee ne peut pas etre validee.")
    entry.status = RegistryEntry.STATUS_COMPLETED
    return _clean_instance(entry)


@transaction.atomic
def archive_registry_entry(entry):
    if entry.is_archived:
        raise ValidationError("Cette entree est deja archivee.")
    entry.is_archived = True
    entry.is_active = False
    if entry.status == RegistryEntry.STATUS_IN_PROGRESS:
        entry.status = RegistryEntry.STATUS_COMPLETED
    return _clean_instance(entry)


@transaction.atomic
def link_registry_to_student(entry, student):
    entry.related_student = student
    return _clean_instance(entry)


@transaction.atomic
def register_visitor(*, created_by, **data):
    visitor = VisitorLog(created_by=created_by, **data)
    if not visitor.status:
        visitor.status = VisitorLog.STATUS_IN_PROGRESS
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
    return _clean_instance(appointment)


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
def complete_appointment(appointment):
    if appointment.is_archived:
        raise ValidationError("Un rendez-vous archive ne peut pas etre complete.")
    if appointment.status == Appointment.STATUS_COMPLETED:
        raise ValidationError("Ce rendez-vous est deja termine.")
    appointment.status = Appointment.STATUS_COMPLETED
    return _clean_instance(appointment)


@transaction.atomic
def register_document(*, received_by, **data):
    document = DocumentReceipt(received_by=received_by, **data)
    return _clean_instance(document)


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
def archive_document(document):
    if document.is_archived:
        raise ValidationError("Ce document est deja archive.")
    document.is_archived = True
    document.is_active = False
    if document.status == DocumentReceipt.STATUS_IN_PROGRESS:
        document.status = DocumentReceipt.STATUS_COMPLETED
    return _clean_instance(document)


@transaction.atomic
def link_document_to_registry(document, registry_entry):
    document.related_registry = registry_entry
    return _clean_instance(document)


def get_recent_documents(limit=5, *, user=None, branch=None):
    return get_recent_documents_queryset(limit=limit, user=user, branch=branch)


@transaction.atomic
def create_task(*, created_by, **data):
    task = SecretaryTask(created_by=created_by, **data)
    return _clean_instance(task)


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


def get_student_snapshot(student_id, *, user=None, branch=None):
    student = get_object_or_404(get_student_snapshot_queryset(student_id, user=user, branch=branch))
    enrollment = get_student_active_enrollment(student)
    inscription = getattr(student, "inscription", None)
    candidature = getattr(inscription, "candidature", None)
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
    }


def get_secretary_dashboard_data(user):
    branch = get_user_branch(user)
    active_students = get_active_students(user=user, branch=branch)
    today_appointments = get_today_appointments(user=user, branch=branch)
    today_visits = get_today_visits(user=user, branch=branch)
    active_visits = get_active_visits(user=user, branch=branch)
    pending_tasks = get_pending_tasks(user=user, branch=branch)
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


def assign_student_to_class_if_needed(*args, **kwargs):
    return None
