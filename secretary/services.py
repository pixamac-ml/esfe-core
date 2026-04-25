from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import Appointment, DocumentReceipt, RegistryEntry, SecretaryTask, VisitorLog
from .selectors import (
    get_active_students,
    get_active_visits_queryset,
    get_recent_documents_queryset,
    get_recent_registry_entries,
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
def update_registry_entry(entry, **data):
    for field, value in data.items():
        setattr(entry, field, value)
    return _clean_instance(entry)


@transaction.atomic
def mark_registry_processed(entry):
    entry.status = RegistryEntry.STATUS_COMPLETED
    return _clean_instance(entry)


@transaction.atomic
def archive_registry_entry(entry):
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
    if visitor.departed_at:
        raise ValidationError("Cette visite est deja cloturee.")

    visitor.departed_at = departed_at or timezone.now()
    visitor.status = VisitorLog.STATUS_COMPLETED
    return _clean_instance(visitor)


def get_active_visits():
    return get_active_visits_queryset()


def get_today_visits():
    return get_today_visits_queryset()


@transaction.atomic
def create_appointment(*, created_by, **data):
    scheduled_at = data.get("scheduled_at")
    assigned_to = data.get("assigned_to")
    prevent_conflicts(scheduled_at=scheduled_at, assigned_to=assigned_to)
    appointment = Appointment(created_by=created_by, **data)
    return _clean_instance(appointment)


@transaction.atomic
def validate_appointment(appointment):
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


def get_today_appointments():
    return get_today_appointments_queryset()


@transaction.atomic
def complete_appointment(appointment):
    appointment.status = Appointment.STATUS_COMPLETED
    return _clean_instance(appointment)


@transaction.atomic
def register_document(*, received_by, **data):
    document = DocumentReceipt(received_by=received_by, **data)
    return _clean_instance(document)


@transaction.atomic
def archive_document(document):
    document.is_archived = True
    document.is_active = False
    if document.status == DocumentReceipt.STATUS_IN_PROGRESS:
        document.status = DocumentReceipt.STATUS_COMPLETED
    return _clean_instance(document)


@transaction.atomic
def link_document_to_registry(document, registry_entry):
    document.related_registry = registry_entry
    return _clean_instance(document)


def get_recent_documents(limit=5):
    return get_recent_documents_queryset(limit=limit)


@transaction.atomic
def create_task(*, created_by, **data):
    task = SecretaryTask(created_by=created_by, **data)
    return _clean_instance(task)


@transaction.atomic
def assign_task(task, user):
    task.assigned_to = user
    if task.status == SecretaryTask.STATUS_PENDING:
        task.status = SecretaryTask.STATUS_IN_PROGRESS
    return _clean_instance(task)


@transaction.atomic
def complete_task(task):
    task.status = SecretaryTask.STATUS_COMPLETED
    return _clean_instance(task)


def get_pending_tasks():
    return SecretaryTask.objects.select_related(
        "assigned_to",
        "related_student__user",
    ).filter(
        status__in=[SecretaryTask.STATUS_PENDING, SecretaryTask.STATUS_IN_PROGRESS],
        is_archived=False,
        is_active=True,
    ).order_by("due_date", "-created_at")


def search_students(query):
    return search_students_queryset(query)


def search_academic_classes(query):
    return search_classes(query)


def get_student_snapshot(student_id):
    student = get_object_or_404(get_student_snapshot_queryset(student_id))
    enrollment = get_student_active_enrollment(student)
    candidature = student.inscription.candidature
    return {
        "student_id": student.id,
        "full_name": student.full_name,
        "matricule": student.matricule,
        "email": student.email,
        "programme": getattr(candidature.programme, "title", ""),
        "branch": getattr(candidature.branch, "name", ""),
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
    active_students = get_active_students()
    today_appointments = get_today_appointments()
    today_visits = get_today_visits()
    active_visits = get_active_visits()
    pending_tasks = get_pending_tasks()

    return {
        "students_count": active_students.count(),
        "appointments_today": today_appointments.count(),
        "visits_today": today_visits.count(),
        "active_visits": active_visits.count(),
        "pending_tasks": pending_tasks.count(),
        "recent_registry": get_recent_registry_entries(limit=5),
        "recent_documents": get_recent_documents(limit=5),
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
