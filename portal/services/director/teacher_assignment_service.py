from collections import defaultdict
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Q

from academics.models import AcademicScheduleEvent, WeeklyScheduleSlot
from portal.models import DirectorTeacherAssignment


def build_director_teacher_assignment_context(*, branch, schedule_stats, teacher_q=""):
    User = get_user_model()
    teachers = User.objects.select_related("profile").filter(is_active=True, profile__position="teacher")
    if branch:
        teachers = teachers.filter(profile__branch=branch)
    if teacher_q:
        teachers = teachers.filter(
            Q(first_name__icontains=teacher_q)
            | Q(last_name__icontains=teacher_q)
            | Q(username__icontains=teacher_q)
            | Q(email__icontains=teacher_q)
            | Q(profile__employee_code__icontains=teacher_q)
        )

    teacher_ids = list(teachers.values_list("id", flat=True))
    weekly_slots = WeeklyScheduleSlot.objects.select_related("academic_class", "ec", "teacher").filter(
        teacher_id__in=teacher_ids,
        is_active=True,
    )
    if branch:
        weekly_slots = weekly_slots.filter(branch=branch)

    planned_events = AcademicScheduleEvent.objects.select_related("academic_class", "ec", "teacher").filter(
        teacher_id__in=teacher_ids,
        is_active=True,
    )
    if branch:
        planned_events = planned_events.filter(branch=branch)

    slots_by_teacher = defaultdict(list)
    classes_by_teacher = defaultdict(dict)
    ecs_by_teacher = defaultdict(dict)
    for slot in weekly_slots:
        slots_by_teacher[slot.teacher_id].append(slot)
        classes_by_teacher[slot.teacher_id][slot.academic_class_id] = slot.academic_class.display_name
        ecs_by_teacher[slot.teacher_id][slot.ec_id] = slot.ec.title

    events_by_teacher = defaultdict(list)
    for event in planned_events.order_by("start_datetime", "id"):
        events_by_teacher[event.teacher_id].append(event)
        classes_by_teacher[event.teacher_id][event.academic_class_id] = event.academic_class.display_name
        ecs_by_teacher[event.teacher_id][event.ec_id] = event.ec.title

    assignments = DirectorTeacherAssignment.objects.select_related("academic_class", "ec").filter(
        teacher_id__in=teacher_ids,
        is_active=True,
    )
    if branch:
        assignments = assignments.filter(branch=branch)
    for assignment in assignments:
        if assignment.academic_class_id:
            classes_by_teacher[assignment.teacher_id][assignment.academic_class_id] = assignment.academic_class.display_name
        if assignment.ec_id:
            ecs_by_teacher[assignment.teacher_id][assignment.ec_id] = assignment.ec.title

    teacher_load_map = schedule_stats.get("teacher_load") or {}
    teacher_rows = []
    for teacher in teachers.order_by("first_name", "last_name", "username")[:150]:
        teacher_key = teacher.get_full_name() or teacher.username
        load = teacher_load_map.get(teacher_key, {"count": 0, "hours": Decimal("0")})
        slot_items = slots_by_teacher.get(teacher.id, [])
        event_items = events_by_teacher.get(teacher.id, [])
        class_labels = list(classes_by_teacher.get(teacher.id, {}).values())
        ec_labels = list(ecs_by_teacher.get(teacher.id, {}).values())
        has_assignment = bool(classes_by_teacher.get(teacher.id) or ecs_by_teacher.get(teacher.id))
        teacher_rows.append({
            "teacher": teacher,
            "label": teacher_key,
            "email": teacher.email or "Email non renseigne",
            "hours": load.get("hours", Decimal("0")),
            "count": load.get("count", 0),
            "status": getattr(getattr(teacher, "profile", None), "employment_status", "active"),
            "status_label": getattr(getattr(teacher, "profile", None), "get_employment_status_display", lambda: "Actif")(),
            "branch_name": getattr(getattr(teacher, "profile", None), "branch", None).name if getattr(getattr(teacher, "profile", None), "branch", None) else "",
            "employee_code": getattr(getattr(teacher, "profile", None), "employee_code", "") or "Code absent",
            "class_labels": class_labels[:6],
            "ec_labels": ec_labels[:8],
            "slot_count": len(slot_items),
            "event_count": len(event_items),
            "first_events": event_items[:4],
            "has_load": bool(load.get("count") or slot_items or event_items or has_assignment),
        })

    return {
        "teacher_rows": teacher_rows,
        "teachers_total": len(teacher_rows),
        "teacher_unassigned_count": sum(1 for item in teacher_rows if not item["has_load"]),
    }
