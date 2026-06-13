from decimal import Decimal

from django.db.models import Avg, Count, Prefetch, Sum
from django.core.cache import cache
from django.utils import timezone

from academics.models import AcademicScheduleEvent, EC, ECContent, ECGrade, StudentContentProgress, WeeklyScheduleSlot
from academics.services.schedule_service import get_student_week_schedule
from communication.selectors import get_user_notifications
from communication.models import CommunicationNotification
from news.models import Event
from payments.models import Payment
from .profile_service import get_profile_completion, get_profile_data
from portal.student.widgets.academics import get_academics_widget
from portal.student.widgets.academics import get_student_academic_snapshot


def _get_student_branch(student, enrollment):
    candidature = getattr(getattr(student, "inscription", None), "candidature", None)
    if candidature and candidature.branch_id:
        return candidature.branch
    return getattr(enrollment, "branch", None)


def _format_decimal(value, suffix=""):
    if value is None:
        return "Non disponible"
    if isinstance(value, Decimal):
        text = f"{value:.2f}".rstrip("0").rstrip(".")
    else:
        text = str(value)
    return f"{text}{suffix}"


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
    grade = getattr(ec, "_student_grade", None)
    final_score = getattr(grade, "final_score", None) if grade else None
    credit_obtained = getattr(grade, "credit_obtained", None) if grade else None
    is_validated = bool(getattr(grade, "is_validated", False)) if grade else False
    has_grade = grade is not None and final_score is not None
    if has_grade and is_validated:
        status_label = "Valide"
        status_tone = "success"
    elif has_grade:
        status_label = "Non valide"
        status_tone = "danger"
    else:
        status_label = "Note en attente"
        status_tone = "warning"

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
        "credit_obtained": _format_decimal(credit_obtained),
        "final_score": _format_decimal(final_score, "/20") if has_grade else "En attente",
        "is_validated": is_validated,
        "has_grade": has_grade,
        "status_label": status_label,
        "status_tone": status_tone,
        "content_count": content_count,
        "has_content": content_count > 0,
    }


def _apply_course_semester_unlocks(courses):
    semester_numbers = sorted({int(course["semester"]) for course in courses})
    completion_by_semester = {}
    for semester in semester_numbers:
        semester_courses = [course for course in courses if int(course["semester"]) == semester]
        completion_by_semester[semester] = bool(semester_courses) and all(
            course["is_validated"] for course in semester_courses
        )

    for course in courses:
        semester = int(course["semester"])
        previous_semesters = [number for number in semester_numbers if number < semester]
        semester_unlocked = all(completion_by_semester.get(number, False) for number in previous_semesters)
        course["semester_label"] = f"S{semester}"
        course["semester_unlocked"] = semester_unlocked
        course["semester_lock_message"] = (
            ""
            if semester_unlocked
            else f"Terminez et validez les EC des semestres precedents avant d'ouvrir S{semester}."
        )
    return courses


def _build_course_semester_filters(courses):
    semesters = {}
    for course in courses:
        number = int(course["semester"])
        row = semesters.setdefault(
            number,
            {
                "number": str(number),
                "label": f"S{number}",
                "unlocked": False,
                "total": 0,
                "validated": 0,
            },
        )
        row["total"] += 1
        if course["is_validated"]:
            row["validated"] += 1
        row["unlocked"] = row["unlocked"] or bool(course["semester_unlocked"])

    filters = []
    for number in sorted(semesters):
        row = semesters[number]
        row["hint"] = (
            f"{row['validated']}/{row['total']} EC valides"
            if row["unlocked"]
            else f"Verrouille - {row['validated']}/{row['total']} EC valides"
        )
        filters.append(row)
    return filters


def is_semester_unlocked_for_enrollment(enrollment, semester_number):
    if enrollment is None:
        return False
    semester_number = int(semester_number)
    previous_ec_ids = list(
        EC.objects.filter(
            ue__semester__academic_class=enrollment.academic_class,
            ue__semester__number__lt=semester_number,
        ).values_list("id", flat=True)
    )
    if not previous_ec_ids:
        return True
    validated_count = (
        ECGrade.objects.filter(
            enrollment=enrollment,
            ec_id__in=previous_ec_ids,
            is_validated=True,
        )
        .values("ec_id")
        .distinct()
        .count()
    )
    return validated_count == len(previous_ec_ids)


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
        ec._student_grade = None

    grade_by_ec_id = {}
    if enrollment is not None:
        grade_by_ec_id = {
            grade.ec_id: grade
            for grade in ECGrade.objects.filter(enrollment=enrollment).select_related("ec")
        }

    for ec in ecs:
        ec._student_grade = grade_by_ec_id.get(ec.id)

    return _apply_course_semester_unlocks([_serialize_course(ec) for ec in ecs])


def get_student_results_summary(student):
    snapshot = get_student_academic_snapshot(student.user)
    enrollment = snapshot["academic_enrollment"]
    ecs = snapshot["academic_ecs"]
    if enrollment is None:
        return {
            "average": "Non disponible",
            "validated_count": 0,
            "failed_count": 0,
            "pending_count": 0,
            "credits_obtained": Decimal("0"),
            "credits_required": Decimal("0"),
            "credits_label": "0/0",
            "validation_rate": 0,
            "semester_rows": [],
            "grade_rows": [],
        }

    grades = list(
        ECGrade.objects.select_related("ec", "ec__ue", "ec__ue__semester")
        .filter(enrollment=enrollment)
        .order_by("ec__ue__semester__number", "ec__ue__code", "ec__title")
    )
    grade_by_ec_id = {grade.ec_id: grade for grade in grades}
    credits_required = sum((ec.credit_required or Decimal("0")) for ec in ecs)
    credits_obtained = sum((grade.credit_obtained or Decimal("0")) for grade in grades)
    scored = [grade.final_score for grade in grades if grade.final_score is not None]
    average = sum(scored) / len(scored) if scored else None
    validated_count = sum(1 for grade in grades if grade.is_validated)
    failed_count = sum(1 for grade in grades if grade.final_score is not None and not grade.is_validated)
    pending_count = max(len(ecs) - len(scored), 0)
    validation_rate = round((validated_count / len(ecs)) * 100) if ecs else 0

    semester_map = {}
    grade_rows = []
    for ec in ecs:
        grade = grade_by_ec_id.get(ec.id)
        semester_number = ec.ue.semester.number
        bucket = semester_map.setdefault(
            semester_number,
            {
                "semester": f"S{semester_number}",
                "ec_count": 0,
                "validated_count": 0,
                "credits_required": Decimal("0"),
                "credits_obtained": Decimal("0"),
                "scores": [],
            },
        )
        bucket["ec_count"] += 1
        bucket["credits_required"] += ec.credit_required or Decimal("0")
        if grade:
            bucket["credits_obtained"] += grade.credit_obtained or Decimal("0")
            if grade.is_validated:
                bucket["validated_count"] += 1
            if grade.final_score is not None:
                bucket["scores"].append(grade.final_score)

        grade_rows.append(
            {
                "semester": f"S{semester_number}",
                "code": ec.ue.code,
                "title": ec.title,
                "coefficient": _format_decimal(ec.coefficient),
                "credit_required": _format_decimal(ec.credit_required),
                "credit_obtained": _format_decimal(getattr(grade, "credit_obtained", None) if grade else None),
                "final_score": _format_decimal(getattr(grade, "final_score", None), "/20") if grade and grade.final_score is not None else "En attente",
                "is_validated": bool(getattr(grade, "is_validated", False)),
                "has_grade": bool(grade and grade.final_score is not None),
            }
        )

    semester_rows = []
    for number in sorted(semester_map):
        row = semester_map[number]
        score_avg = sum(row["scores"]) / len(row["scores"]) if row["scores"] else None
        semester_rows.append(
            {
                "semester": row["semester"],
                "ec_count": row["ec_count"],
                "validated_count": row["validated_count"],
                "credits": f"{_format_decimal(row['credits_obtained'])}/{_format_decimal(row['credits_required'])}",
                "average": _format_decimal(score_avg, "/20") if score_avg is not None else "En attente",
                "progress": round((row["validated_count"] / row["ec_count"]) * 100) if row["ec_count"] else 0,
            }
        )

    return {
        "average": _format_decimal(average, "/20") if average is not None else "Non disponible",
        "average_raw": average,
        "validated_count": validated_count,
        "failed_count": failed_count,
        "pending_count": pending_count,
        "credits_obtained": credits_obtained,
        "credits_required": credits_required,
        "credits_label": f"{_format_decimal(credits_obtained)}/{_format_decimal(credits_required)}",
        "validation_rate": validation_rate,
        "semester_rows": semester_rows,
        "grade_rows": grade_rows,
    }


def get_student_teachers(student):
    from portal.models import DirectorTeacherAssignment

    snapshot = get_student_academic_snapshot(student.user)
    enrollment = snapshot["academic_enrollment"]
    if enrollment is None:
        return []

    active_statuses = {
        AcademicScheduleEvent.STATUS_DRAFT,
        AcademicScheduleEvent.STATUS_PLANNED,
        AcademicScheduleEvent.STATUS_ONGOING,
        AcademicScheduleEvent.STATUS_POSTPONED,
    }
    teachers = {}
    assignments = (
        DirectorTeacherAssignment.objects.select_related(
            "teacher",
            "teacher__profile",
            "ec",
            "ec__ue",
            "ec__ue__semester",
        )
        .filter(academic_class=enrollment.academic_class, is_active=True)
        .order_by("teacher__last_name", "teacher__first_name", "ec__ue__semester__number", "ec__title")
    )
    weekly_slots = (
        WeeklyScheduleSlot.objects.select_related("teacher", "teacher__profile", "ec", "ec__ue", "ec__ue__semester")
        .filter(academic_class=enrollment.academic_class, is_active=True)
        .order_by("weekday", "start_time", "id")
    )
    upcoming_events = (
        AcademicScheduleEvent.objects.select_related("teacher", "teacher__profile", "ec", "ec__ue", "ec__ue__semester")
        .filter(
            academic_class=enrollment.academic_class,
            is_active=True,
            status__in=active_statuses,
            start_datetime__gte=timezone.now(),
        )
        .order_by("start_datetime", "id")[:80]
    )

    def teacher_name(user):
        full_name = user.get_full_name().strip()
        return full_name or user.get_username()

    def ensure_teacher(user):
        profile = getattr(user, "profile", None)
        row = teachers.setdefault(
            user.id,
            {
                "id": user.id,
                "name": teacher_name(user),
                "initials": "".join(part[:1] for part in teacher_name(user).split()[:2]).upper() or "EN",
                "email": user.email or "Non renseigne",
                "phone": getattr(profile, "phone", "") or "Non renseigne",
                "avatar_url": getattr(profile, "avatar_url", ""),
                "position": getattr(profile, "get_position_display", lambda: "")() or "Enseignant",
                "bio": getattr(profile, "bio", "") or "",
                "subjects": [],
                "subject_codes": [],
                "semesters": set(),
                "rooms": [],
                "planned_hours": Decimal("0"),
                "assignment_count": 0,
                "weekly_slots": [],
                "event_count": 0,
                "next_course": None,
            },
        )
        return row

    for assignment in assignments:
        row = ensure_teacher(assignment.teacher)
        if assignment.ec_id:
            if assignment.ec.title not in row["subjects"]:
                row["subjects"].append(assignment.ec.title)
            if assignment.ec.ue.code not in row["subject_codes"]:
                row["subject_codes"].append(assignment.ec.ue.code)
            row["semesters"].add(assignment.ec.ue.semester.number)
        if assignment.room_label and assignment.room_label not in row["rooms"]:
            row["rooms"].append(assignment.room_label)
        if assignment.planned_hours is not None:
            row["planned_hours"] += assignment.planned_hours
        row["assignment_count"] += 1

    for slot in weekly_slots:
        row = ensure_teacher(slot.teacher)
        if slot.ec.title not in row["subjects"]:
            row["subjects"].append(slot.ec.title)
        if slot.ec.ue.code not in row["subject_codes"]:
            row["subject_codes"].append(slot.ec.ue.code)
        row["semesters"].add(slot.ec.ue.semester.number)
        row["weekly_slots"].append(
            {
                "day": slot.get_weekday_display(),
                "time": f"{slot.start_time:%H:%M}-{slot.end_time:%H:%M}",
                "room": slot.room or "Salle non precisee",
                "subject": slot.ec.title,
            }
        )

    for event in upcoming_events:
        row = ensure_teacher(event.teacher)
        row["event_count"] += 1
        if event.ec.title not in row["subjects"]:
            row["subjects"].append(event.ec.title)
        if event.ec.ue.code not in row["subject_codes"]:
            row["subject_codes"].append(event.ec.ue.code)
        row["semesters"].add(event.ec.ue.semester.number)
        if row["next_course"] is None:
            start_at = timezone.localtime(event.start_datetime)
            end_at = timezone.localtime(event.end_datetime)
            row["next_course"] = {
                "title": event.ec.title,
                "date": start_at.strftime("%d/%m"),
                "time": f"{start_at:%H:%M}-{end_at:%H:%M}",
                "location": event.location or "Salle non precisee",
            }

    payload = []
    for row in teachers.values():
        subjects = row["subjects"]
        row["subject"] = subjects[0] if subjects else "Matiere non renseignee"
        row["subjects_label"] = ", ".join(subjects[:3]) + ("..." if len(subjects) > 3 else "")
        row["codes_label"] = ", ".join(row["subject_codes"][:4]) or "Codes EC non renseignes"
        row["semesters_label"] = ", ".join(f"S{number}" for number in sorted(row["semesters"])) or "Semestre non renseigne"
        row["rooms_label"] = ", ".join(row["rooms"][:3]) or "Salle non precisee"
        row["planned_hours_label"] = (
            _format_decimal(row["planned_hours"], " h")
            if row["planned_hours"]
            else "Volume non precise"
        )
        row["weekly_count"] = len(row["weekly_slots"])
        row["weekly_slots"] = row["weekly_slots"][:3]
        payload.append(row)

    return sorted(payload, key=lambda item: item["name"])[:12]


def get_student_stats(student):
    snapshot = get_student_academic_snapshot(student.user)
    enrollment = snapshot["academic_enrollment"]
    courses = snapshot["academic_ecs"]

    total_credits = sum((ec.credit_required or 0) for ec in courses)
    payments = Payment.objects.filter(inscription=student.inscription, status=Payment.STATUS_VALIDATED)
    total_paid = payments.aggregate(total=Sum("amount"))["total"] or 0
    total_due = getattr(student.inscription, "amount_due", 0) or 0
    results = get_student_results_summary(student)

    return {
        "average": results["average"],
        "ranking": f"{results['validated_count']} EC valides",
        "completed_courses": len(courses),
        "credits": total_credits,
        "credits_obtained": results["credits_obtained"],
        "payments_validated": payments.count(),
        "remaining_amount": max(total_due - total_paid, 0),
        "enrollment_status": "Affecte" if enrollment else "En attente",
        "mini_stats": [
            {"label": "Cours suivis", "value": len(courses), "icon": "book-open"},
            {"label": "Credits obtenus", "value": results["credits_label"], "icon": "badge-check"},
            {"label": "Paiements valides", "value": payments.count(), "icon": "wallet"},
            {"label": "Messages", "value": len(get_student_messages(student)), "icon": "mail"},
        ],
        "progress_bars": [
            {"label": "EC valides", "value": results["validation_rate"]},
            {"label": "Credits acquis", "value": min(round((results["credits_obtained"] / total_credits) * 100), 100) if total_credits else 0},
            {"label": "Paiement", "value": min(int((total_paid / total_due) * 100), 100) if total_due else 0},
        ],
        "results": results,
    }


def get_student_timetable(student):
    return get_student_week_schedule(student, None)


def get_student_next_course(student):
    timetable = get_student_timetable(student)
    events = timetable.get("events", []) if isinstance(timetable, dict) else []
    now = timezone.now()
    active_statuses = {"planned", "ongoing", "postponed", "draft"}

    for event in events:
        start_at = event.get("start_datetime")
        if not start_at:
            continue
        if event.get("status") not in active_statuses:
            continue
        if start_at >= now:
            return {
                "title": event.get("title") or "Cours",
                "time_range": event.get("time_range") or "--:-- - --:--",
                "weekday_label": event.get("weekday_label") or "",
                "location": event.get("location") or "Salle non precisee",
                "is_online": bool(event.get("is_online")),
            }

    return None


def get_student_priority_actions(student, *, snapshot, next_course=None, stats=None):
    if student is None:
        return [
            {
                "label": "Finaliser le rattachement",
                "description": "Votre compte etudiant est en cours de finalisation.",
                "icon": "user-check",
                "target": "settings",
                "nav_label": "Parametres",
                "tone": "warning",
            }
        ]

    completion = get_profile_completion(student.user)
    stats = stats or get_student_stats(student)
    actions = []

    if next_course:
        actions.append(
            {
                "label": "Prochain cours",
                "description": f"{next_course['title']} - {next_course['time_range']}",
                "icon": "clock-3",
                "target": "schedule",
                "nav_label": "Calendrier",
                "tone": "primary",
            }
        )

    if not completion["is_complete"]:
        actions.append(
            {
                "label": "Completer mon profil",
                "description": completion["message"],
                "icon": "id-card",
                "target": "settings",
                "nav_label": "Parametres",
                "tone": "warning" if completion["alert_level"] == "warning" else "danger",
            }
        )

    unread_count = get_student_unread_messages_count(student)
    if unread_count:
        actions.append(
            {
                "label": "Lire mes messages",
                "description": f"{unread_count} message(s) non lu(s).",
                "icon": "messages-square",
                "target": "messages",
                "nav_label": "Messages",
                "tone": "primary",
            }
        )

    remaining_amount = stats.get("remaining_amount") or 0
    if remaining_amount:
        actions.append(
            {
                "label": "Verifier ma finance",
                "description": f"Reste a regler: {remaining_amount} FCFA.",
                "icon": "wallet",
                "target": "settings",
                "nav_label": "Parametres",
                "tone": "warning",
            }
        )

    if snapshot["academic_status"] != "assigned":
        actions.append(
            {
                "label": "Suivre mon affectation",
                "description": snapshot["academic_status_message"],
                "icon": "graduation-cap",
                "target": "academics",
                "nav_label": "Academique",
                "tone": "warning",
            }
        )

    actions.append(
        {
            "label": "Reprendre mes cours",
            "description": f"{stats.get('completed_courses', 0)} cours disponible(s).",
            "icon": "book-open-check",
            "target": "courses",
            "nav_label": "Mes cours",
            "tone": "neutral",
        }
    )

    return actions[:4]


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
    communication_items = list(
        get_user_notifications(
            student.user,
            limit=24,
            channel=CommunicationNotification.CHANNEL_IN_APP,
        )
    )
    return [_serialize_student_notification(item) for item in communication_items]


def _notification_excerpt(body, limit=150):
    text = " ".join((body or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _notification_category(item):
    haystack = f"{item.title} {item.body} {item.notification_type} {item.event_type}".lower()
    if any(word in haystack for word in ["note", "resultat", "academ", "cours", "classe", "semestre", "matiere"]):
        return "Academique"
    if any(word in haystack for word in ["paiement", "recu", "finance", "frais", "solde", "facture"]):
        return "Finance"
    if any(word in haystack for word in ["evenement", "event", "calendrier", "agenda", "rendez-vous"]):
        return "Evenement"
    if any(word in haystack for word in ["inscription", "affectation", "dossier", "document"]):
        return "Administratif"
    if any(word in haystack for word in ["boutique", "commande", "article"]):
        return "Boutique"
    return "Systeme"


def _notification_visuals(category, priority):
    by_category = {
        "Academique": ("graduation-cap", "primary"),
        "Finance": ("wallet", "warning"),
        "Evenement": ("calendar-days", "primary"),
        "Administratif": ("folder-check", "neutral"),
        "Boutique": ("shopping-bag", "neutral"),
        "Systeme": ("bell-ring", "neutral"),
    }
    icon, tone = by_category.get(category, ("bell-ring", "neutral"))
    if priority == CommunicationNotification.PRIORITY_CRITICAL:
        return icon, "danger"
    if priority == CommunicationNotification.PRIORITY_HIGH:
        return icon, "warning"
    return icon, tone


def _serialize_student_notification(item):
    category = _notification_category(item)
    icon, tone = _notification_visuals(category, item.priority)
    is_read = bool(item.read_at)
    return {
        "id": item.id,
        "name": item.title,
        "text": _notification_excerpt(item.body, 120),
        "body": _notification_excerpt(item.body, 420),
        "time": item.created_at.strftime("%d/%m"),
        "datetime": item.created_at.strftime("%d/%m/%Y %H:%M"),
        "avatar": "",
        "is_read": is_read,
        "read_label": "Lu" if is_read else "Non lu",
        "category": category,
        "icon": icon,
        "tone": tone,
        "priority": item.get_priority_display() if hasattr(item, "get_priority_display") else item.priority,
        "source": item.legacy_source or item.event_type or item.notification_type or "systeme",
    }


def get_student_message_summary(student):
    qs = CommunicationNotification.objects.filter(
        recipient=student.user,
        channel=CommunicationNotification.CHANNEL_IN_APP,
    )
    items = list(qs.order_by("-created_at")[:100])
    categories = {}
    for item in items:
        label = _notification_category(item)
        icon, tone = _notification_visuals(label, item.priority)
        bucket = categories.setdefault(
            label,
            {"label": label, "count": 0, "unread": 0, "icon": icon, "tone": tone},
        )
        bucket["count"] += 1
        if item.read_at is None:
            bucket["unread"] += 1
    unread = qs.filter(read_at__isnull=True).count()
    last_item = items[0] if items else None
    return {
        "total": qs.count(),
        "unread": unread,
        "read": max(qs.count() - unread, 0),
        "last_activity": last_item.created_at.strftime("%d/%m/%Y %H:%M") if last_item else "Aucune activite",
        "categories": sorted(categories.values(), key=lambda row: (row["unread"] == 0, row["label"])),
    }


def get_student_notification_events(student):
    events = get_student_events(student)
    return [
        {
            "title": event["title"],
            "text": event["desc"],
            "time": f"{event['day']} {event['month']}",
            "branch": event["branch"],
            "icon": "calendar-days",
        }
        for event in events[:3]
    ]


def get_student_unread_messages_count(student):
    return CommunicationNotification.objects.filter(
        recipient=student.user,
        channel=CommunicationNotification.CHANNEL_IN_APP,
        read_at__isnull=True,
    ).count()


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
            "next_course": None,
            "events": [],
            "messages": [],
            "teachers": [],
            "unread_messages_count": 0,
            "priority_actions": get_student_priority_actions(None, snapshot=snapshot),
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
            "academic_widget": get_academics_widget(user),
            "page_title": "Dashboard etudiant",
            "subtitle": "Vue d'ensemble de votre parcours academique",
        }

    timetable = get_student_timetable(student)
    next_course = get_student_next_course(student)
    stats = get_student_stats(student)
    return {
        "student": student,
        "enrollment": enrollment,
        "courses": get_student_courses(student),
        "teachers": get_student_teachers(student),
        "timetable": timetable,
        "next_course": next_course,
        "events": get_student_events(student),
        "messages": get_student_messages(student),
        "unread_messages_count": get_student_unread_messages_count(student),
        "stats": stats,
        "results": stats["results"],
        "message_summary": get_student_message_summary(student),
        "priority_actions": get_student_priority_actions(
            student,
            snapshot=snapshot,
            next_course=next_course,
            stats=stats,
        ),
        "academic_status": snapshot["academic_status"],
        "academic_status_message": snapshot["academic_status_message"],
        "academic_widget": get_academics_widget(user),
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
            "timetable": {},
            "next_course": None,
            "events": [],
            "messages": [],
            "unread_messages_count": 0,
            "priority_actions": get_student_priority_actions(None, snapshot=snapshot),
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
            "academic_widget": get_academics_widget(user),
            "academic_class": snapshot["academic_class"],
            "academic_programme": snapshot["academic_programme"],
            "academic_year": snapshot["academic_year"],
            "academic_level": snapshot["academic_level"],
            "page_title": "Dashboard etudiant",
            "subtitle": "Vue d'ensemble de votre parcours academique",
        }

    # Overview: hero + stats + courses overview + profile + events
    timetable = get_student_timetable(student)
    next_course = get_student_next_course(student)
    stats = get_student_stats(student)
    return {
        "student": student,
        "enrollment": enrollment,
        "courses": get_student_courses(student),
        "timetable": timetable,
        "next_course": next_course,
        "events": get_student_events(student),
        "messages": get_student_messages(student),
        "teachers": get_student_teachers(student),
        "unread_messages_count": get_student_unread_messages_count(student),
        "stats": stats,
        "results": stats["results"],
        "message_summary": get_student_message_summary(student),
        "priority_actions": get_student_priority_actions(
            student,
            snapshot=snapshot,
            next_course=next_course,
            stats=stats,
        ),
        "academic_status": snapshot["academic_status"],
        "academic_status_message": snapshot["academic_status_message"],
        "academic_widget": get_academics_widget(user),
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
    courses = get_student_courses(student) if student else []
    return {
        "courses": courses,
        "course_semesters": _build_course_semester_filters(courses),
        "results": get_student_results_summary(student) if student else {},
        "academic_status": snapshot["academic_status"],
        "academic_status_message": snapshot["academic_status_message"],
    }


def get_student_messages_context(user):
    snapshot = get_student_academic_snapshot(user)
    student = snapshot["student"]
    if not student:
        return {
            "messages": [],
            "unread_messages_count": 0,
            "message_summary": {"total": 0, "unread": 0, "read": 0, "last_activity": "Aucune activite", "categories": []},
            "notification_events": [],
        }
    return {
        "messages": get_student_messages(student),
        "unread_messages_count": get_student_unread_messages_count(student),
        "message_summary": get_student_message_summary(student),
        "notification_events": get_student_notification_events(student),
    }


def get_student_timetable_context(user):
    snapshot = get_student_academic_snapshot(user)
    student = snapshot["student"]
    return {"timetable": get_student_timetable(student) if student else {}}
