from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from academics.models import AcademicClass, AcademicEnrollment
from community.models import Notification
from students.models import Student

from .models import Appointment, DocumentReceipt, RegistryEntry, SecretaryTask, VisitorLog

User = get_user_model()


def _apply_common_filters(queryset, filters):
    filters = filters or {}
    q = (filters.get("q") or "").strip()
    status = (filters.get("status") or "").strip()
    archived = filters.get("archived")
    active_only = filters.get("active_only")

    if status:
        queryset = queryset.filter(status=status)

    if archived in {True, False}:
        queryset = queryset.filter(is_archived=archived)

    if active_only in {True, False}:
        queryset = queryset.filter(is_active=active_only)

    return queryset, q


def get_registry_queryset(filters=None):
    queryset = RegistryEntry.objects.select_related(
        "created_by",
        "related_student__user",
        "related_staff",
    )
    queryset, q = _apply_common_filters(queryset, filters)
    if q:
        queryset = queryset.filter(
            Q(title__icontains=q)
            | Q(description__icontains=q)
            | Q(entry_type__icontains=q)
            | Q(related_student__matricule__icontains=q)
            | Q(related_student__user__username__icontains=q)
        )
    return queryset


def get_appointments_queryset(filters=None):
    queryset = Appointment.objects.select_related(
        "created_by",
        "assigned_to",
        "related_student__user",
        "related_staff",
    )
    queryset, q = _apply_common_filters(queryset, filters)
    if q:
        queryset = queryset.filter(
            Q(title__icontains=q)
            | Q(person_name__icontains=q)
            | Q(phone__icontains=q)
            | Q(email__icontains=q)
            | Q(reason__icontains=q)
            | Q(related_student__matricule__icontains=q)
        )

    date_from = filters.get("date_from") if filters else None
    if date_from:
        queryset = queryset.filter(scheduled_at__date__gte=date_from)

    date_to = filters.get("date_to") if filters else None
    if date_to:
        queryset = queryset.filter(scheduled_at__date__lte=date_to)

    return queryset


def get_visits_queryset(filters=None):
    queryset = VisitorLog.objects.select_related(
        "created_by",
        "related_student__user",
        "related_staff",
    )
    queryset, q = _apply_common_filters(queryset, filters)
    if q:
        queryset = queryset.filter(
            Q(full_name__icontains=q)
            | Q(phone__icontains=q)
            | Q(reason__icontains=q)
            | Q(related_student__matricule__icontains=q)
        )
    return queryset


def get_documents_queryset(filters=None):
    queryset = DocumentReceipt.objects.select_related(
        "received_by",
        "related_student__user",
        "related_registry",
    )
    queryset, q = _apply_common_filters(queryset, filters)
    if q:
        queryset = queryset.filter(
            Q(title__icontains=q)
            | Q(description__icontains=q)
            | Q(submitted_by_name__icontains=q)
            | Q(related_student__matricule__icontains=q)
            | Q(related_registry__title__icontains=q)
        )
    return queryset


def get_tasks_queryset(filters=None):
    queryset = SecretaryTask.objects.select_related(
        "assigned_to",
        "created_by",
        "related_student__user",
    )
    queryset, q = _apply_common_filters(queryset, filters)
    if q:
        queryset = queryset.filter(
            Q(title__icontains=q)
            | Q(description__icontains=q)
            | Q(priority__icontains=q)
            | Q(related_student__matricule__icontains=q)
            | Q(assigned_to__username__icontains=q)
        )
    return queryset


def get_active_students():
    return Student.objects.select_related(
        "user",
        "inscription__candidature__programme",
        "inscription__candidature__branch",
    ).filter(is_active=True)


def get_students_by_class(academic_class):
    return Student.objects.select_related(
        "user",
        "inscription__candidature__programme",
    ).filter(
        academic_enrollments__academic_class=academic_class,
        academic_enrollments__is_active=True,
    )


def search_students(query):
    queryset = get_active_students()
    if not query:
        return queryset.none()
    return queryset.filter(
        Q(matricule__icontains=query)
        | Q(user__username__icontains=query)
        | Q(inscription__candidature__first_name__icontains=query)
        | Q(inscription__candidature__last_name__icontains=query)
        | Q(inscription__candidature__email__icontains=query)
    )


def search_classes(query):
    queryset = AcademicClass.objects.select_related(
        "programme",
        "branch",
        "academic_year",
    ).filter(is_active=True)
    if not query:
        return queryset.none()
    return queryset.filter(
        Q(name__icontains=query)
        | Q(level__icontains=query)
        | Q(programme__title__icontains=query)
        | Q(branch__name__icontains=query)
        | Q(academic_year__name__icontains=query)
    )


def get_student_snapshot_queryset(student_id):
    return Student.objects.select_related(
        "user",
        "inscription__candidature__programme",
        "inscription__candidature__branch",
    ).prefetch_related(
        "registry_entries",
        "appointments",
        "visitor_logs",
        "document_receipts",
        "secretary_tasks",
        "user__academic_enrollments__academic_class__academic_year",
    ).filter(id=student_id)


def get_recent_registry_entries(limit=5):
    return get_registry_queryset({"archived": False})[:limit]


def get_pending_tasks(limit=None):
    queryset = get_tasks_queryset(
        {
            "status": SecretaryTask.STATUS_PENDING,
            "archived": False,
            "active_only": True,
        }
    )
    if limit:
        return queryset[:limit]
    return queryset


def get_secretary_notifications(user, limit=10):
    return Notification.objects.select_related("actor", "topic", "answer").filter(user=user)[:limit]


def get_user_messages(user, limit=20):
    return Notification.objects.select_related("actor", "topic", "answer").filter(user=user)[:limit]


def get_unread_messages_count(user):
    return Notification.objects.filter(user=user, is_read=False).count()


def get_today_appointments_queryset():
    return get_appointments_queryset({"date_from": timezone.localdate(), "date_to": timezone.localdate()})


def get_today_visits_queryset():
    today = timezone.localdate()
    return get_visits_queryset({}).filter(arrived_at__date=today)


def get_active_visits_queryset():
    return get_visits_queryset(
        {
            "status": VisitorLog.STATUS_IN_PROGRESS,
            "archived": False,
            "active_only": True,
        }
    )


def get_recent_documents_queryset(limit=5):
    return get_documents_queryset({"archived": False})[:limit]


def get_student_active_enrollment(student):
    return (
        AcademicEnrollment.objects.select_related(
            "academic_class",
            "academic_year",
            "programme",
            "branch",
        )
        .filter(student=student.user, is_active=True)
        .order_by("-created_at")
        .first()
    )
