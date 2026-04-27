from django.db.models import Prefetch, Sum
from django.core.cache import cache

from academics.models import EC, ECContent, StudentContentProgress
from academics.services.schedule_service import get_student_week_schedule
from community.models import Notification as CommunityNotification
from core.models import Notification as CoreNotification
from news.models import Event
from payments.models import Payment
from .profile_service import get_profile_data
from portal.student.widgets.academics import get_student_academic_snapshot


def _get_student_branch(student, enrollment):
    candidature = getattr(getattr(student, "inscription", None), "candidature", None)
    if candidature and candidature.branch_id:
        return candidature.branch
    return getattr(enrollment, "branch", None)


def _serialize_course(ec):
    contents = [
        content
        for chapter in getattr(ec, "chapters", []).all()
        for content in chapter.contents.all()
        if getattr(content, "is_active", True)
    ]
    content_count = len(contents)
    progress_entries = getattr(ec, "_student_progress_entries", [])
    progress_by_content_id = {entry.content_id: entry for entry in progress_entries}
    progress_values = [
        progress_by_content_id[content.id].progress_percent
        for content in contents
        if content.id in progress_by_content_id
    ]
    progress_percent = round(sum(progress_values) / content_count) if content_count else 0

    return {
        "id": ec.id,
        "title": ec.title,
        "teacher": "Enseignant non renseigne",
        "progress": progress_percent,
        "icon": "book-open",
        "ue": ec.ue.title,
        "semester": ec.ue.semester.number,
        "code": ec.ue.code,
        "coefficient": ec.coefficient,
        "credit_required": ec.credit_required,
        "content_count": content_count,
    }


def get_student_courses(student):
    snapshot = get_student_academic_snapshot(student.user)
    enrollment = snapshot["academic_enrollment"]
    if enrollment is None:
        return []

    ecs = (
        EC.objects.select_related(
            "ue",
            "ue__semester",
            "ue__semester__academic_class",
        )
        .prefetch_related(
            Prefetch(
                "chapters__contents",
                queryset=ECContent.objects.filter(is_active=True).order_by("order", "id"),
            )
        )
        .filter(ue__semester__academic_class=enrollment.academic_class)
        .order_by("ue__semester__number", "ue__code", "id")
    )

    progress_entries = list(
        StudentContentProgress.objects.filter(
            student=student.user,
            content__chapter__ec__ue__semester__academic_class=enrollment.academic_class,
            content__is_active=True,
        ).select_related("content")
    )
    progress_by_ec_id = {}
    for entry in progress_entries:
        progress_by_ec_id.setdefault(entry.content.chapter.ec_id, []).append(entry)

    for ec in ecs:
        ec._student_progress_entries = progress_by_ec_id.get(ec.id, [])

    return [_serialize_course(ec) for ec in ecs]


def get_student_teachers(student):
    snapshot = get_student_academic_snapshot(student.user)
    enrollment = snapshot["academic_enrollment"]
    if enrollment is None:
        return []

    week_schedule = get_student_week_schedule(student, None)
    teachers = {}
    for event in week_schedule["events"]:
        teacher_name = event["teacher_name"]
        if teacher_name not in teachers:
            teachers[teacher_name] = {
                "name": teacher_name,
                "subject": event["title"],
            }
    return list(teachers.values())[:6]


def get_student_stats(student):
    snapshot = get_student_academic_snapshot(student.user)
    enrollment = snapshot["academic_enrollment"]
    courses = snapshot["academic_ecs"]

    total_credits = sum((ec.credit_required or 0) for ec in courses)
    payments = Payment.objects.filter(inscription=student.inscription, status=Payment.STATUS_VALIDATED)
    total_paid = payments.aggregate(total=Sum("amount"))["total"] or 0
    total_due = getattr(student.inscription, "amount_due", 0) or 0

    return {
        "average": "Non disponible",
        "ranking": "Non disponible",
        "completed_courses": len(courses),
        "credits": total_credits,
        "payments_validated": payments.count(),
        "remaining_amount": max(total_due - total_paid, 0),
        "enrollment_status": "Affecte" if enrollment else "En attente",
        "mini_stats": [
            {"label": "Cours suivis", "value": len(courses), "icon": "book-open"},
            {"label": "Credits", "value": total_credits, "icon": "badge-check"},
            {"label": "Paiements valides", "value": payments.count(), "icon": "wallet"},
            {"label": "Messages", "value": len(get_student_messages(student)), "icon": "mail"},
        ],
        "progress_bars": [
            {"label": "Cours actifs", "value": min(len(courses) * 12, 100)},
            {"label": "Credits acquis", "value": min(int(total_credits * 3), 100)},
            {"label": "Paiement", "value": min(int((total_paid / total_due) * 100), 100) if total_due else 0},
        ],
    }


def get_student_timetable(student):
    return get_student_week_schedule(student, None)


def get_student_events(student):
    snapshot = get_student_academic_snapshot(student.user)
    branch = _get_student_branch(student, snapshot["academic_enrollment"])

    cache_key = f"portal_student:events:v1:branch:{getattr(branch, 'id', 'none')}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    events = Event.objects.filter(is_published=True).order_by("event_date")[:4]
    payload = [
        {
            "day": event.event_date.strftime("%d"),
            "month": event.event_date.strftime("%b").upper(),
            "title": event.title,
            "desc": event.description[:90] + ("..." if len(event.description) > 90 else ""),
            "branch": getattr(branch, "name", ""),
        }
        for event in events
    ]
    cache.set(cache_key, payload, 30)
    return payload


def get_student_messages(student):
    cache_key = f"portal_student:messages:v1:user:{getattr(getattr(student, 'user', None), 'id', 'anon')}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    email = getattr(student, "email", "")
    core_items = list(
        CoreNotification.objects.filter(recipient_email=email)
        .order_by("-created_at")
        .values("title", "message", "created_at")[:3]
    )
    if core_items:
        payload = [
            {
                "name": item["title"],
                "text": item["message"][:90] + ("..." if len(item["message"]) > 90 else ""),
                "time": item["created_at"].strftime("%d/%m"),
                "avatar": "",
            }
            for item in core_items
        ]
        cache.set(cache_key, payload, 30)
        return payload

    community_items = (
        CommunityNotification.objects.select_related("actor")
        .filter(user=student.user)
        .order_by("-created_at")[:3]
    )
    payload = [
        {
            "name": item.actor.get_full_name() or item.actor.username,
            "text": item.get_notification_type_display(),
            "time": item.created_at.strftime("%d/%m"),
            "avatar": "",
        }
        for item in community_items
    ]
    cache.set(cache_key, payload, 30)
    return payload


def get_student_dashboard_data(user):
    snapshot = get_student_academic_snapshot(user)
    student = snapshot["student"]
    enrollment = snapshot["academic_enrollment"]

    if student is None:
        return {
            "student": None,
            "enrollment": None,
            "courses": [],
            "teachers": [],
            "timetable": [],
            "events": [],
            "messages": [],
            "stats": {
                "average": "Non disponible",
                "ranking": "Non disponible",
                "completed_courses": 0,
                "credits": 0,
                "payments_validated": 0,
                "remaining_amount": 0,
                "enrollment_status": "En attente",
                "mini_stats": [],
                "progress_bars": [],
            },
            "academic_status": snapshot["academic_status"],
            "academic_status_message": snapshot["academic_status_message"],
            "page_title": "Dashboard etudiant",
            "subtitle": "Vue d'ensemble de votre parcours academique",
        }

    return {
        "student": student,
        "enrollment": enrollment,
        "courses": get_student_courses(student),
        "teachers": get_student_teachers(student),
        "timetable": get_student_timetable(student),
        "events": get_student_events(student),
        "messages": get_student_messages(student),
        "stats": get_student_stats(student),
        "academic_status": snapshot["academic_status"],
        "academic_status_message": snapshot["academic_status_message"],
        "academic_class": snapshot["academic_class"],
        "academic_programme": snapshot["academic_programme"],
        "academic_year": snapshot["academic_year"],
        "academic_level": snapshot["academic_level"],
        "profile_settings": get_profile_data(user),
        "page_title": "Dashboard etudiant",
        "subtitle": "Vue d'ensemble de votre parcours academique",
    }


def get_student_dashboard_shell(user):
    return get_student_dashboard_data(user)


def get_student_overview_data(user):
    """
    Donnees minimales pour le rendu initial (section overview uniquement).
    Les autres sections sont chargees a la demande via HTMX.
    """
    snapshot = get_student_academic_snapshot(user)
    student = snapshot["student"]
    enrollment = snapshot["academic_enrollment"]

    if student is None:
        return {
            "student": None,
            "enrollment": None,
            "courses": [],
            "events": [],
            "messages": [],
            "stats": {
                "average": "Non disponible",
                "ranking": "Non disponible",
                "completed_courses": 0,
                "credits": 0,
                "payments_validated": 0,
                "remaining_amount": 0,
                "enrollment_status": "En attente",
                "mini_stats": [],
                "progress_bars": [],
            },
            "academic_status": snapshot["academic_status"],
            "academic_status_message": snapshot["academic_status_message"],
            "academic_class": snapshot["academic_class"],
            "academic_programme": snapshot["academic_programme"],
            "academic_year": snapshot["academic_year"],
            "academic_level": snapshot["academic_level"],
            "page_title": "Dashboard etudiant",
            "subtitle": "Vue d'ensemble de votre parcours academique",
        }

    # Overview: hero + stats + courses overview + profile + events
    return {
        "student": student,
        "enrollment": enrollment,
        "courses": get_student_courses(student),
        "events": get_student_events(student),
        "messages": get_student_messages(student),
        "stats": get_student_stats(student),
        "academic_status": snapshot["academic_status"],
        "academic_status_message": snapshot["academic_status_message"],
        "academic_class": snapshot["academic_class"],
        "academic_programme": snapshot["academic_programme"],
        "academic_year": snapshot["academic_year"],
        "academic_level": snapshot["academic_level"],
        "page_title": "Dashboard etudiant",
        "subtitle": "Vue d'ensemble de votre parcours academique",
    }


def get_student_courses_context(user):
    snapshot = get_student_academic_snapshot(user)
    student = snapshot["student"]
    return {
        "courses": get_student_courses(student) if student else [],
        "academic_status": snapshot["academic_status"],
        "academic_status_message": snapshot["academic_status_message"],
    }


def get_student_messages_context(user):
    snapshot = get_student_academic_snapshot(user)
    student = snapshot["student"]
    return {"messages": get_student_messages(student) if student else []}


def get_student_timetable_context(user):
    snapshot = get_student_academic_snapshot(user)
    student = snapshot["student"]
    return {"timetable": get_student_timetable(student) if student else {}}
