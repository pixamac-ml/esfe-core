from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.db import OperationalError, ProgrammingError
from django.db.models import Count, Prefetch, Q
from django.utils import timezone

from academics.models import AcademicClass, AcademicScheduleEvent, EC, ECChapter, ECContent, LessonLog, WeeklyScheduleSlot
from academics.services.lesson_log_service import get_teacher_lesson_logs
from academics.services.schedule_service import get_teacher_next_events, get_teacher_week_schedule
from accounts.models import UserPreference
from portal.models import AccountSupportState
from students.models import Student, TeacherAttendance
from portal.models import TeacherDashboardPreference

WEEKDAY_LABELS = [
    "Lundi",
    "Mardi",
    "Mercredi",
    "Jeudi",
    "Vendredi",
    "Samedi",
    "Dimanche",
]


def _teacher_dashboard_preference_defaults():
    return {
        "dark_mode": False,
        "sidebar_collapsed": False,
        "compact_mode": False,
        "default_section": TeacherDashboardPreference.DEFAULT_OVERVIEW,
        "notify_lesson_reminders": True,
        "notify_schedule_changes": True,
        "notify_support_messages": True,
    }


def get_teacher_dashboard_preference(*, teacher, branch):
    if branch is None:
        return SimpleNamespace(**_teacher_dashboard_preference_defaults())
    try:
        preference, _created = TeacherDashboardPreference.objects.get_or_create(
            teacher=teacher,
            branch=branch,
            defaults=_teacher_dashboard_preference_defaults(),
        )
        return preference
    except (OperationalError, ProgrammingError):
        return SimpleNamespace(**_teacher_dashboard_preference_defaults())


def serialize_teacher_dashboard_preference(preference):
    if preference is None:
        preference = SimpleNamespace(**_teacher_dashboard_preference_defaults())
    return {
        "dark_mode": preference.dark_mode,
        "sidebar_collapsed": preference.sidebar_collapsed,
        "compact_mode": preference.compact_mode,
        "default_section": preference.default_section,
        "notify_lesson_reminders": preference.notify_lesson_reminders,
        "notify_schedule_changes": preference.notify_schedule_changes,
        "notify_support_messages": preference.notify_support_messages,
    }


def update_teacher_dashboard_preference(
    *,
    actor,
    teacher,
    branch,
    dark_mode,
    sidebar_collapsed,
    compact_mode,
    default_section,
    notify_lesson_reminders,
    notify_schedule_changes,
    notify_support_messages,
):
    if branch is None:
        raise ValidationError("Aucune annexe rattachee pour le compte enseignant.")

    preference = get_teacher_dashboard_preference(teacher=teacher, branch=branch)
    allowed_sections = {choice[0] for choice in TeacherDashboardPreference.DEFAULT_SECTION_CHOICES}
    default_section = (default_section or TeacherDashboardPreference.DEFAULT_OVERVIEW).strip()
    if default_section not in allowed_sections:
        raise ValidationError("La section d'ouverture selectionnee est invalide.")

    preference.dark_mode = bool(dark_mode)
    preference.sidebar_collapsed = bool(sidebar_collapsed)
    preference.compact_mode = bool(compact_mode)
    preference.default_section = default_section
    preference.notify_lesson_reminders = bool(notify_lesson_reminders)
    preference.notify_schedule_changes = bool(notify_schedule_changes)
    preference.notify_support_messages = bool(notify_support_messages)
    preference.updated_by = actor
    if hasattr(preference, "full_clean"):
        preference.full_clean()
        preference.save()
    return preference


def _serialize_class_focus(academic_class, *, event_count, slot_count, subjects, next_event):
    return {
        "class_id": academic_class.id,
        "class_name": academic_class.display_name,
        "programme_title": getattr(academic_class.programme, "title", ""),
        "academic_year_name": getattr(academic_class.academic_year, "name", ""),
        "student_count": getattr(academic_class, "student_count", 0),
        "event_count": event_count,
        "slot_count": slot_count,
        "subjects": sorted(subjects),
        "subjects_count": len(subjects),
        "next_event": next_event,
    }


def _get_teacher_director_assignments(*, teacher, branch, academic_class=None):
    from portal.models import DirectorTeacherAssignment

    assignments_qs = DirectorTeacherAssignment.objects.select_related(
        "academic_class",
        "academic_class__programme",
        "academic_class__academic_year",
        "academic_class__branch",
        "ec",
        "ec__ue",
    ).filter(
        teacher=teacher,
        is_active=True,
    )
    if branch is not None:
        assignments_qs = assignments_qs.filter(branch=branch)
    if academic_class is not None:
        assignments_qs = assignments_qs.filter(academic_class=academic_class)
    return list(assignments_qs)


def _resolve_teacher_class(*, teacher, branch, class_id):
    academic_class = (
        AcademicClass.objects.select_related(
            "programme",
            "academic_year",
            "branch",
        )
        .annotate(student_count=Count("enrollments", filter=Q(enrollments__is_active=True), distinct=True))
        .filter(pk=class_id, is_active=True)
        .first()
    )
    if academic_class is None:
        raise ValidationError("Classe introuvable.")
    if branch is not None and academic_class.branch_id != branch.id:
        raise ValidationError("Cette classe n'appartient pas a votre annexe.")

    has_assignment = AcademicScheduleEvent.objects.filter(
        academic_class=academic_class,
        teacher=teacher,
        is_active=True,
    ).exclude(status=AcademicScheduleEvent.STATUS_CANCELLED).exists() or WeeklyScheduleSlot.objects.filter(
        academic_class=academic_class,
        teacher=teacher,
        is_active=True,
    ).exists()
    if not has_assignment:
        has_assignment = bool(
            _get_teacher_director_assignments(
                teacher=teacher,
                branch=branch,
                academic_class=academic_class,
            )
        )
    if not has_assignment:
        raise ValidationError("Cette classe n'est pas rattachee a cet enseignant.")
    return academic_class


def _content_prefetch():
    return Prefetch(
        "contents",
        queryset=ECContent.objects.order_by("order", "id"),
    )


def _chapter_prefetch():
    return Prefetch(
        "chapters",
        queryset=ECChapter.objects.prefetch_related(_content_prefetch()).order_by("order", "id"),
    )


def _get_teacher_class_queryset(*, teacher, branch):
    event_class_ids = list(
        AcademicScheduleEvent.objects.filter(
            teacher=teacher,
            is_active=True,
        )
        .exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
        .values_list("academic_class_id", flat=True)
    )
    slot_class_ids = list(
        WeeklyScheduleSlot.objects.filter(
            teacher=teacher,
            is_active=True,
        ).values_list("academic_class_id", flat=True)
    )
    assignment_class_ids = [
        assignment.academic_class_id
        for assignment in _get_teacher_director_assignments(teacher=teacher, branch=branch)
        if assignment.academic_class_id
    ]
    class_ids = {class_id for class_id in [*event_class_ids, *slot_class_ids, *assignment_class_ids] if class_id}
    queryset = AcademicClass.objects.select_related(
        "programme",
        "academic_year",
        "branch",
    ).annotate(
        student_count=Count("enrollments", filter=Q(enrollments__is_active=True), distinct=True),
    ).filter(
        pk__in=class_ids,
        is_active=True,
    )
    if branch is not None:
        queryset = queryset.filter(branch=branch)
    return queryset.order_by("programme__title", "level", "id")


def _get_teacher_ecs_for_class(*, teacher, branch, academic_class):
    event_ec_ids = list(
        AcademicScheduleEvent.objects.filter(
            teacher=teacher,
            academic_class=academic_class,
            is_active=True,
        )
        .exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
        .values_list("ec_id", flat=True)
    )
    slot_ec_ids = list(
        WeeklyScheduleSlot.objects.filter(
            teacher=teacher,
            academic_class=academic_class,
            is_active=True,
        ).values_list("ec_id", flat=True)
    )
    assignment_ec_ids = [
        assignment.ec_id
        for assignment in _get_teacher_director_assignments(
            teacher=teacher,
            branch=branch,
            academic_class=academic_class,
        )
        if assignment.ec_id
    ]
    ec_ids = {ec_id for ec_id in [*event_ec_ids, *slot_ec_ids, *assignment_ec_ids] if ec_id}

    queryset = (
        EC.objects.select_related(
            "ue",
            "ue__semester",
            "ue__semester__academic_class",
        )
        .prefetch_related(_chapter_prefetch())
        .filter(
            pk__in=ec_ids,
            ue__semester__academic_class=academic_class,
        )
        .order_by("ue__code", "title", "id")
    )
    if branch is not None:
        queryset = queryset.filter(ue__semester__academic_class__branch=branch)
    return list(queryset)


def _resolve_teacher_ec(*, teacher, branch, academic_class, ec_id):
    for ec in _get_teacher_ecs_for_class(
        teacher=teacher,
        branch=branch,
        academic_class=academic_class,
    ):
        if ec.id == ec_id:
            return ec
    raise ValidationError("Cette matiere n'est pas rattachee a cet enseignant pour la classe choisie.")


def _parse_positive_int(raw_value, *, field_label, default=0, allow_zero=True):
    value = (raw_value or "").strip()
    if not value:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field_label} invalide.")
    minimum = 0 if allow_zero else 1
    if parsed < minimum:
        raise ValidationError(f"{field_label} invalide.")
    return parsed


def _validate_content_file_extension(*, content_type, uploaded_file):
    if not uploaded_file:
        return
    extension = Path(uploaded_file.name or "").suffix.lower()
    allowed_extensions = {
        ECContent.CONTENT_TYPE_PDF: {".pdf"},
        ECContent.CONTENT_TYPE_DOC: {".doc", ".docx"},
        ECContent.CONTENT_TYPE_EXCEL: {".xls", ".xlsx", ".csv"},
        ECContent.CONTENT_TYPE_PPT: {".ppt", ".pptx"},
        ECContent.CONTENT_TYPE_VIDEO: {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"},
        ECContent.CONTENT_TYPE_IMAGE: {".png", ".jpg", ".jpeg", ".gif", ".webp"},
        ECContent.CONTENT_TYPE_AUDIO: {".mp3", ".wav", ".ogg", ".m4a"},
    }.get(content_type)
    if allowed_extensions and extension not in allowed_extensions:
        raise ValidationError("Le format du fichier ne correspond pas au type de contenu choisi.")


def _serialize_support_content(content):
    file_name = Path(content.file.name).name if content.file else ""
    text_content = (content.text_content or "").strip()
    video_url = (content.video_url or "").strip()
    return {
        "id": content.id,
        "title": content.title,
        "content_type": content.content_type,
        "content_type_label": content.get_content_type_display(),
        "file_name": file_name,
        "file_url": content.file.url if content.file else "",
        "video_url": video_url,
        "text_content": text_content,
        "text_excerpt": f"{text_content[:140]}..." if len(text_content) > 140 else text_content,
        "order": content.order,
        "is_video": content.content_type == ECContent.CONTENT_TYPE_VIDEO,
        "is_file_based": bool(content.file),
        "has_video_url": bool(video_url),
        "has_text_content": bool(text_content),
    }


def _serialize_support_chapter(chapter):
    contents = [_serialize_support_content(content) for content in chapter.contents.all()]
    return {
        "id": chapter.id,
        "title": chapter.title,
        "order": chapter.order,
        "content_count": len(contents),
        "contents": contents,
    }


def _serialize_support_ec(ec):
    chapters = [_serialize_support_chapter(chapter) for chapter in ec.chapters.all()]
    return {
        "id": ec.id,
        "title": ec.title,
        "ue_code": getattr(getattr(ec, "ue", None), "code", ""),
        "chapters": chapters,
        "chapter_count": len(chapters),
        "content_count": sum(chapter["content_count"] for chapter in chapters),
    }


def build_teacher_support_workspace_context(request, *, branch, class_id=None, ec_id=None, chapter_id=None, toast=None):
    teacher = request.user
    class_queryset = list(_get_teacher_class_queryset(teacher=teacher, branch=branch))
    if not class_queryset:
        return {
            "branch": branch,
            "toast": toast,
            "teacher_support_classes": [],
            "selected_class": None,
            "selected_ec": None,
            "selected_ec_summary": None,
            "selected_chapter": None,
            "teacher_support_ecs": [],
            "teacher_support_chapters": [],
            "teacher_support_contents": [],
            "content_type_choices": ECContent.CONTENT_TYPE_CHOICES,
            "file_content_type_choices": [
                choice for choice in ECContent.CONTENT_TYPE_CHOICES
                if choice[0] != ECContent.CONTENT_TYPE_TEXT
            ],
        }

    selected_class = None
    if class_id is not None:
        selected_class = _resolve_teacher_class(teacher=teacher, branch=branch, class_id=class_id)
    else:
        selected_class = class_queryset[0]

    teacher_support_classes = [
        _serialize_class_focus(
            academic_class,
            event_count=AcademicScheduleEvent.objects.filter(
                teacher=teacher,
                academic_class=academic_class,
                is_active=True,
            ).exclude(status=AcademicScheduleEvent.STATUS_CANCELLED).count(),
            slot_count=WeeklyScheduleSlot.objects.filter(
                teacher=teacher,
                academic_class=academic_class,
                is_active=True,
            ).count(),
            subjects={ec.title for ec in _get_teacher_ecs_for_class(teacher=teacher, branch=branch, academic_class=academic_class)},
            next_event=None,
        )
        for academic_class in class_queryset
    ]

    teacher_support_ecs = _get_teacher_ecs_for_class(teacher=teacher, branch=branch, academic_class=selected_class)
    selected_ec = None
    if teacher_support_ecs:
        if ec_id is not None:
            selected_ec = _resolve_teacher_ec(teacher=teacher, branch=branch, academic_class=selected_class, ec_id=ec_id)
        else:
            selected_ec = teacher_support_ecs[0]

    teacher_support_chapters = []
    selected_chapter = None
    teacher_support_contents = []
    if selected_ec is not None:
        teacher_support_chapters = [_serialize_support_chapter(chapter) for chapter in selected_ec.chapters.all()]
        if chapter_id is not None:
            for chapter in selected_ec.chapters.all():
                if chapter.id == chapter_id:
                    selected_chapter = chapter
                    break
            if selected_chapter is None:
                raise ValidationError("Ce chapitre n'est pas rattache a la matiere selectionnee.")
        elif teacher_support_chapters:
            selected_chapter = selected_ec.chapters.all()[0]
        if selected_chapter is not None:
            teacher_support_contents = [_serialize_support_content(content) for content in selected_chapter.contents.all()]

    return {
        "branch": branch,
        "toast": toast,
        "teacher_support_classes": teacher_support_classes,
        "selected_class": selected_class,
        "teacher_support_ecs": [_serialize_support_ec(ec) for ec in teacher_support_ecs],
        "selected_ec": selected_ec,
        "selected_ec_summary": _serialize_support_ec(selected_ec) if selected_ec is not None else None,
        "teacher_support_chapters": teacher_support_chapters,
        "selected_chapter": selected_chapter,
        "teacher_support_contents": teacher_support_contents,
        "content_type_choices": ECContent.CONTENT_TYPE_CHOICES,
        "file_content_type_choices": [
            choice for choice in ECContent.CONTENT_TYPE_CHOICES
            if choice[0] != ECContent.CONTENT_TYPE_TEXT
        ],
    }


def build_teacher_dashboard_context(request, *, branch, base_context_builder):
    teacher = request.user
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=7)
    now = timezone.now()

    teacher_events_qs = (
        AcademicScheduleEvent.objects.select_related(
            "academic_class",
            "academic_class__programme",
            "academic_class__academic_year",
            "teacher",
            "ec",
            "ec__ue",
            "branch",
            "academic_year",
        )
        .filter(
            teacher=teacher,
            is_active=True,
        )
        .exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
    )
    if branch is not None:
        teacher_events_qs = teacher_events_qs.filter(branch=branch)

    today_events = list(
        teacher_events_qs
        .filter(start_datetime__date=today)
        .order_by("start_datetime", "id")
    )
    week_events = list(
        teacher_events_qs
        .filter(start_datetime__date__gte=week_start, start_datetime__date__lt=week_end)
        .order_by("start_datetime", "id")
    )
    upcoming_events = get_teacher_next_events(teacher, limit=12)
    if branch is not None:
        upcoming_events = [event for event in upcoming_events if event.get("branch_name") == branch.name]
    upcoming_events = upcoming_events[:8]

    week_schedule = get_teacher_week_schedule(teacher, week_start)
    if branch is not None:
        week_schedule_events = [
            event for event in week_schedule.get("events", [])
            if event.get("branch_name") == branch.name
        ]
        week_schedule = {
            **week_schedule,
            "events": week_schedule_events,
        }

    weekly_slots_qs = (
        WeeklyScheduleSlot.objects.select_related(
            "academic_class",
            "academic_class__programme",
            "academic_class__academic_year",
            "teacher",
            "ec",
        )
        .filter(teacher=teacher, is_active=True)
        .order_by("academic_class__level", "academic_class__programme__title", "weekday", "start_time")
    )
    if branch is not None:
        weekly_slots_qs = weekly_slots_qs.filter(branch=branch)
    weekly_slots = list(weekly_slots_qs)
    director_assignments = _get_teacher_director_assignments(teacher=teacher, branch=branch)

    class_map = {}
    next_event_by_class = {}
    for event in week_events:
        class_entry = class_map.setdefault(
            event.academic_class_id,
            {
                "academic_class": event.academic_class,
                "event_count": 0,
                "slot_count": 0,
                "subjects": set(),
                "ec_ids": set(),
            },
        )
        class_entry["event_count"] += 1
        if event.ec_id:
            class_entry["subjects"].add(event.ec.title)
            class_entry["ec_ids"].add(event.ec_id)
        if event.academic_class_id not in next_event_by_class and event.start_datetime >= now:
            next_event_by_class[event.academic_class_id] = event

    for slot in weekly_slots:
        class_entry = class_map.setdefault(
            slot.academic_class_id,
            {
                "academic_class": slot.academic_class,
                "event_count": 0,
                "slot_count": 0,
                "subjects": set(),
                "ec_ids": set(),
            },
        )
        class_entry["slot_count"] += 1
        if slot.ec_id:
            class_entry["subjects"].add(slot.ec.title)
            class_entry["ec_ids"].add(slot.ec_id)

    for assignment in director_assignments:
        if assignment.academic_class_id is None:
            continue
        class_entry = class_map.setdefault(
            assignment.academic_class_id,
            {
                "academic_class": assignment.academic_class,
                "event_count": 0,
                "slot_count": 0,
                "subjects": set(),
                "ec_ids": set(),
            },
        )
        if assignment.ec_id:
            class_entry["subjects"].add(assignment.ec.title)
            class_entry["ec_ids"].add(assignment.ec_id)

    class_student_counts = {
        row["pk"]: row["student_count"]
        for row in AcademicClass.objects.filter(pk__in=class_map.keys())
        .annotate(student_count=Count("enrollments", filter=Q(enrollments__is_active=True), distinct=True))
        .values("pk", "student_count")
    }
    for class_id, item in class_map.items():
        setattr(item["academic_class"], "student_count", class_student_counts.get(class_id, 0))

    class_focus_rows = [
        _serialize_class_focus(
            item["academic_class"],
            event_count=item["event_count"],
            slot_count=item["slot_count"],
            subjects=item["subjects"],
            next_event=next_event_by_class.get(class_id),
        )
        for class_id, item in class_map.items()
    ]
    class_focus_rows.sort(key=lambda row: (row["class_name"].lower(), row["programme_title"].lower()))
    subject_titles = sorted(
        {
            subject
            for row in class_focus_rows
            for subject in row["subjects"]
        }
    )
    teacher_ec_ids = {
        ec_id
        for item in class_map.values()
        for ec_id in item.get("ec_ids", set())
        if ec_id
    }

    lesson_logs = get_teacher_lesson_logs(teacher, branch=branch, limit=6)
    lesson_logs_this_week = [
        log for log in lesson_logs
        if week_start <= log.date < week_end
    ]

    logged_event_qs = LessonLog.objects.filter(
        teacher=teacher,
        schedule_event__isnull=False,
        schedule_event__start_datetime__date__gte=week_start,
        schedule_event__start_datetime__date__lt=week_end,
    )
    if branch is not None:
        logged_event_qs = logged_event_qs.filter(branch=branch)
    logged_event_ids = set(logged_event_qs.values_list("schedule_event_id", flat=True))

    completed_or_past_week_events = [event for event in week_events if event.start_datetime <= now]
    pending_lesson_logs = [
        event for event in completed_or_past_week_events
        if event.id not in logged_event_ids
    ]

    monthly_done_logs = LessonLog.objects.filter(
        teacher=teacher,
        date__year=today.year,
        date__month=today.month,
        status=LessonLog.STATUS_DONE,
    )
    if branch is not None:
        monthly_done_logs = monthly_done_logs.filter(branch=branch)

    support_chapters_count = ECChapter.objects.filter(ec_id__in=teacher_ec_ids).count() if teacher_ec_ids else 0
    support_contents_qs = ECContent.objects.filter(chapter__ec_id__in=teacher_ec_ids, is_active=True)
    support_contents_count = support_contents_qs.count() if teacher_ec_ids else 0
    support_file_count = (
        support_contents_qs.exclude(file="").filter(file__isnull=False).count()
        if teacher_ec_ids
        else 0
    )
    support_video_count = (
        support_contents_qs.exclude(video_url="").filter(video_url__isnull=False).count()
        if teacher_ec_ids
        else 0
    )
    support_text_count = support_contents_qs.filter(content_type=ECContent.CONTENT_TYPE_TEXT).count() if teacher_ec_ids else 0

    teacher_attendance_month_qs = TeacherAttendance.objects.filter(
        teacher=teacher,
        date__year=today.year,
        date__month=today.month,
    )
    if branch is not None:
        teacher_attendance_month_qs = teacher_attendance_month_qs.filter(branch=branch)
    teacher_attendance_summary = {
        "present": teacher_attendance_month_qs.filter(status=TeacherAttendance.STATUS_PRESENT).count(),
        "late": teacher_attendance_month_qs.filter(status=TeacherAttendance.STATUS_LATE).count(),
        "absent": teacher_attendance_month_qs.filter(status=TeacherAttendance.STATUS_ABSENT).count(),
        "total": teacher_attendance_month_qs.count(),
    }

    preference = get_teacher_dashboard_preference(teacher=teacher, branch=branch)
    status_summary = {
        "employment_status": getattr(getattr(teacher, "profile", None), "get_employment_status_display", lambda: "Inconnu")(),
        "employee_code": getattr(getattr(teacher, "profile", None), "employee_code", "") or "Non renseigne",
        "branch_name": getattr(branch, "name", "Non rattache"),
        "hire_date": getattr(getattr(teacher, "profile", None), "hire_date", None),
    }

    day_buckets = defaultdict(list)
    for event in week_schedule.get("events", []):
        day_buckets[event["weekday_index"]].append(event)
    scheduled_days_count = len([events for events in day_buckets.values() if events])
    weekly_rooms = {
        location.strip()
        for location in [
            *[event.location or "" for event in week_events],
            *[slot.room or "" for slot in weekly_slots],
        ]
        if location and location.strip()
    }

    teaching_days = []
    for offset, day in enumerate(week_schedule.get("days", [])):
        teaching_days.append(
            {
                "label": day["label"],
                "date": day["date"],
                "is_today": day["is_today"],
                "events": day_buckets.get(offset, []),
            }
        )

    completed_or_past_count = len(completed_or_past_week_events)
    lesson_completion_rate = round(
        ((completed_or_past_count - len(pending_lesson_logs)) / completed_or_past_count) * 100
    ) if completed_or_past_count else 100
    total_students_visible = sum(row.get("student_count", 0) for row in class_focus_rows)
    next_event_focus = upcoming_events[0] if upcoming_events else None
    teacher_insights = []
    if pending_lesson_logs:
        teacher_insights.append(
            {
                "tone": "danger",
                "label": "Cahiers en attente",
                "message": f"{len(pending_lesson_logs)} seance(s) terminee(s) attendent un cahier de texte.",
                "section": "logs",
            }
        )
    if today_events:
        teacher_insights.append(
            {
                "tone": "primary",
                "label": "Cours aujourd'hui",
                "message": f"{len(today_events)} cours programme(s) aujourd'hui.",
                "section": "schedule",
            }
        )
    if support_contents_count == 0 and class_focus_rows:
        teacher_insights.append(
            {
                "tone": "warning",
                "label": "Supports",
                "message": "Aucun support actif n'est encore visible pour vos matieres.",
                "section": "supports",
            }
        )
    if not teacher_insights:
        teacher_insights.append(
            {
                "tone": "success",
                "label": "Situation stable",
                "message": "Aucune action urgente detectee sur le perimetre enseignant.",
                "section": "overview",
            }
        )

    context = {
        **base_context_builder(
            request,
            page_title="Dashboard enseignant",
            module_cards=[
                "Mes cours",
                "Mes classes",
                "Mon journal de cours",
                "Mon planning",
            ],
        ),
        "dashboard_kind": "Enseignant",
        "branch": branch,
        "teacher_dashboard_preference": serialize_teacher_dashboard_preference(preference) if preference is not None else _teacher_dashboard_preference_defaults(),
        "status_summary": status_summary,
        "today": today,
        "week_start": week_start,
        "week_end": week_end - timedelta(days=1),
        "today_events": today_events,
        "upcoming_events": upcoming_events,
        "teaching_days": teaching_days,
        "class_focus_rows": class_focus_rows,
        "recent_lesson_logs": lesson_logs,
        "week_lesson_logs_count": len(lesson_logs_this_week),
        "pending_lesson_logs_count": len(pending_lesson_logs),
        "pending_lesson_log_rows": pending_lesson_logs[:6],
        "has_teacher_activity": bool(
            today_events
            or upcoming_events
            or class_focus_rows
            or lesson_logs
            or pending_lesson_logs
        ),
        "teacher_kpis": {
            "today_courses": len(today_events),
            "week_courses": len(week_events),
            "active_classes": len(class_focus_rows),
            "visible_students": total_students_visible,
            "month_done_logs": monthly_done_logs.count(),
            "subjects_count": len(subject_titles),
            "scheduled_days": scheduled_days_count,
            "weekly_rooms": len(weekly_rooms),
            "support_chapters": support_chapters_count,
            "support_contents": support_contents_count,
            "lesson_completion_rate": lesson_completion_rate,
        },
        "teacher_support_stats": {
            "chapters": support_chapters_count,
            "contents": support_contents_count,
            "files": support_file_count,
            "videos": support_video_count,
            "texts": support_text_count,
        },
        "teacher_attendance_summary": teacher_attendance_summary,
        "next_event_focus": next_event_focus,
        "teacher_insights": teacher_insights,
    }
    return context


def build_teacher_settings_context(request, *, branch, base_context_builder):
    teacher = request.user
    preference = get_teacher_dashboard_preference(teacher=teacher, branch=branch)
    profile = getattr(teacher, "profile", None)
    account_preference, _account_preference_created = UserPreference.objects.get_or_create(user=teacher)
    support_state = AccountSupportState.objects.filter(user=teacher).first()
    status_summary = {
        "employment_status": getattr(profile, "get_employment_status_display", lambda: "Inconnu")(),
        "employee_code": getattr(profile, "employee_code", "") or "Non renseigne",
        "branch_name": getattr(branch, "name", "Non rattache"),
        "hire_date": getattr(profile, "hire_date", None),
    }
    class_ids = set(
        AcademicScheduleEvent.objects.filter(teacher=teacher, is_active=True)
        .exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
        .values_list("academic_class_id", flat=True)
    )
    class_ids.update(
        WeeklyScheduleSlot.objects.filter(teacher=teacher, is_active=True).values_list("academic_class_id", flat=True)
    )
    class_ids.update(
        assignment.academic_class_id
        for assignment in _get_teacher_director_assignments(teacher=teacher, branch=branch)
        if assignment.academic_class_id
    )
    return {
        **base_context_builder(
            request,
            page_title="Dashboard enseignant",
            module_cards=[
                "Mes cours",
                "Mes classes",
                "Mon journal de cours",
                "Mon planning",
            ],
        ),
        "dashboard_kind": "Enseignant",
        "branch": branch,
        "status_summary": status_summary,
        "account_profile_summary": {
            "phone": getattr(profile, "phone", "") or "Non renseigne",
            "location": getattr(profile, "location", "") or "Non renseignee",
            "address": getattr(profile, "address", "") or "Non renseignee",
            "main_domain": getattr(profile, "main_domain", "") or "Non renseigne",
            "bio": getattr(profile, "bio", "") or "",
        },
        "account_preference_summary": {
            "notify_email": account_preference.notify_email,
            "notify_in_app": account_preference.notify_in_app,
            "notify_sms": account_preference.notify_sms,
            "ui_compact_mode": account_preference.ui_compact_mode,
            "ui_sidebar_collapsed": account_preference.ui_sidebar_collapsed,
            "ui_autorefresh": account_preference.ui_autorefresh,
        },
        "account_security_summary": {
            "is_suspended": getattr(support_state, "is_suspended", False),
            "is_blocked": getattr(support_state, "is_blocked", False),
            "must_change_password": getattr(support_state, "must_change_password", False),
        },
        "teacher_dashboard_preference": serialize_teacher_dashboard_preference(preference),
        "teacher_preferences_choices": TeacherDashboardPreference.DEFAULT_SECTION_CHOICES,
        "teacher_settings_stats": {
            "active_classes": len({class_id for class_id in class_ids if class_id}),
            "display_mode": "Compact" if preference.compact_mode else "Standard",
        },
    }


def build_teacher_class_detail_context(request, *, branch, class_id, week_start=None):
    teacher = request.user
    anchor_date = week_start or timezone.localdate()
    normalized_week_start = anchor_date - timedelta(days=anchor_date.weekday())
    week_end = normalized_week_start + timedelta(days=7)
    now = timezone.now()

    academic_class = _resolve_teacher_class(
        teacher=teacher,
        branch=branch,
        class_id=class_id,
    )

    events_qs = (
        AcademicScheduleEvent.objects.select_related(
            "academic_class",
            "academic_class__programme",
            "academic_class__academic_year",
            "ec",
            "ec__ue",
            "teacher",
            "branch",
        )
        .filter(
            academic_class=academic_class,
            teacher=teacher,
            is_active=True,
            start_datetime__date__gte=normalized_week_start,
            start_datetime__date__lt=week_end,
        )
        .exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
        .order_by("start_datetime", "id")
    )
    if branch is not None:
        events_qs = events_qs.filter(branch=branch)
    week_events = list(events_qs)

    weekly_slots_qs = WeeklyScheduleSlot.objects.select_related("ec", "teacher").filter(
        academic_class=academic_class,
        teacher=teacher,
        is_active=True,
    )
    if branch is not None:
        weekly_slots_qs = weekly_slots_qs.filter(branch=branch)
    weekly_slots = list(weekly_slots_qs.order_by("weekday", "start_time", "id"))

    students = list(
        Student.objects.select_related("user", "inscription__candidature")
        .filter(
            is_active=True,
            user__academic_enrollments__academic_class=academic_class,
            user__academic_enrollments__is_active=True,
        )
        .distinct()
        .order_by(
            "inscription__candidature__last_name",
            "inscription__candidature__first_name",
            "matricule",
        )[:80]
    )

    logs_qs = LessonLog.objects.select_related("ec", "schedule_event").filter(
        teacher=teacher,
        academic_class=academic_class,
    )
    if branch is not None:
        logs_qs = logs_qs.filter(branch=branch)
    recent_logs = list(logs_qs.order_by("-date", "-start_time", "-id")[:6])

    next_event = (
        AcademicScheduleEvent.objects.select_related("ec")
        .filter(
            academic_class=academic_class,
            teacher=teacher,
            is_active=True,
            start_datetime__gte=now,
        )
        .exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
        .order_by("start_datetime", "id")
        .first()
    )
    if branch is not None and next_event is not None and next_event.branch_id != branch.id:
        next_event = None

    subject_rows = []
    subjects_seen = set()
    for event in week_events:
        if event.ec_id in subjects_seen:
            continue
        subjects_seen.add(event.ec_id)
        subject_rows.append(
            {
                "title": event.ec.title,
                "ue_code": event.ec.ue.code,
                "room": event.location or "Salle non precisee",
                "event_count": sum(1 for item in week_events if item.ec_id == event.ec_id),
            }
        )
    for slot in weekly_slots:
        if slot.ec_id in subjects_seen:
            continue
        subjects_seen.add(slot.ec_id)
        subject_rows.append(
            {
                "title": slot.ec.title,
                "ue_code": slot.ec.ue.code,
                "room": slot.room or "Salle a definir",
                "event_count": 0,
            }
        )

    weekly_slot_rows = [
        {
            "weekday_label": WEEKDAY_LABELS[slot.weekday] if 0 <= slot.weekday < len(WEEKDAY_LABELS) else f"Jour {slot.weekday + 1}",
            "time_range": f"{slot.start_time.strftime('%H:%M')} - {slot.end_time.strftime('%H:%M')}",
            "room": slot.room or "Salle a definir",
            "ec_title": slot.ec.title,
            "ue_code": slot.ec.ue.code,
        }
        for slot in weekly_slots
    ]

    return {
        "branch": branch,
        "academic_class": academic_class,
        "week_start": normalized_week_start,
        "week_end": week_end - timedelta(days=1),
        "prev_week_start": normalized_week_start - timedelta(days=7),
        "next_week_start": normalized_week_start + timedelta(days=7),
        "students": students,
        "teacher_class_week_events": week_events,
        "teacher_class_weekly_slots": weekly_slots,
        "teacher_class_weekly_slot_rows": weekly_slot_rows,
        "teacher_class_recent_logs": recent_logs,
        "teacher_class_subject_rows": subject_rows,
        "teacher_class_next_event": next_event,
    }


def build_teacher_lesson_log_context(request, *, branch, event_id, toast=None):
    teacher = request.user
    event_qs = AcademicScheduleEvent.objects.select_related(
        "academic_class",
        "academic_class__programme",
        "ec",
        "ec__ue",
        "branch",
        "teacher",
    ).filter(
        pk=event_id,
        teacher=teacher,
        event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
        is_active=True,
    )
    if branch is not None:
        event_qs = event_qs.filter(branch=branch)
    schedule_event = event_qs.first()
    if schedule_event is None:
        raise ValidationError("Cours introuvable pour cet enseignant.")

    log_qs = LessonLog.objects.select_related("schedule_event").filter(
        teacher=teacher,
        schedule_event=schedule_event,
        date=timezone.localdate(schedule_event.start_datetime),
    )
    if branch is not None:
        log_qs = log_qs.filter(branch=branch)
    lesson_log = log_qs.first()

    return {
        "branch": branch,
        "schedule_event": schedule_event,
        "lesson_log": lesson_log,
        "toast": toast,
        "lesson_log_status_choices": [
            (LessonLog.STATUS_DONE, "Fait"),
            (LessonLog.STATUS_CANCELLED, "Annule"),
            (LessonLog.STATUS_PLANNED, "Planifie"),
        ],
    }
