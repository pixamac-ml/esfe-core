from collections import defaultdict
from decimal import Decimal

from django.contrib.auth import get_user_model
from academics.models import AcademicScheduleEvent, WeeklyScheduleSlot
from portal.models import DirectorTeacherAssignment, TeacherDocument


def build_director_teacher_assignment_context(*, branch, schedule_stats, teacher_q="", teacher_scope="all"):
    User = get_user_model()
    teachers = User.objects.none()
    if branch:
        teachers = User.objects.select_related("profile").filter(
            is_active=True,
            profile__position="teacher",
            profile__branch=branch,
        )
    teacher_list = list(teachers.order_by("first_name", "last_name", "username")[:150])
    teacher_ids = [teacher.id for teacher in teacher_list]
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
    rooms_by_teacher = defaultdict(dict)
    planned_hours_by_teacher = defaultdict(Decimal)
    assignments_by_teacher = defaultdict(list)
    for assignment in assignments:
        assignments_by_teacher[assignment.teacher_id].append(assignment)
        if assignment.academic_class_id:
            classes_by_teacher[assignment.teacher_id][assignment.academic_class_id] = assignment.academic_class.display_name
        if assignment.ec_id:
            ecs_by_teacher[assignment.teacher_id][assignment.ec_id] = assignment.ec.title
        if assignment.room_label:
            rooms_by_teacher[assignment.teacher_id][assignment.id] = assignment.room_label
        if assignment.planned_hours is not None:
            planned_hours_by_teacher[assignment.teacher_id] += assignment.planned_hours

    document_count_by_teacher = defaultdict(int)
    pending_document_count_by_teacher = defaultdict(int)
    teacher_documents = TeacherDocument.objects.filter(teacher_id__in=teacher_ids)
    if branch:
        teacher_documents = teacher_documents.filter(branch=branch)
    for document in teacher_documents.only("teacher_id", "is_verified"):
        document_count_by_teacher[document.teacher_id] += 1
        if not document.is_verified:
            pending_document_count_by_teacher[document.teacher_id] += 1

    teacher_load_map = schedule_stats.get("teacher_load") or {}
    teacher_rows = []
    for teacher in teacher_list:
        teacher_key = teacher.get_full_name() or teacher.username
        load = teacher_load_map.get(teacher_key, {"count": 0, "hours": Decimal("0")})
        slot_items = slots_by_teacher.get(teacher.id, [])
        event_items = events_by_teacher.get(teacher.id, [])
        class_labels = list(classes_by_teacher.get(teacher.id, {}).values())
        ec_labels = list(ecs_by_teacher.get(teacher.id, {}).values())
        room_labels = list(rooms_by_teacher.get(teacher.id, {}).values())
        planned_hours_target = planned_hours_by_teacher.get(teacher.id, Decimal("0"))
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
            "room_labels": room_labels[:6],
            "planned_hours_target": planned_hours_target,
            "total_planned_hours": planned_hours_target,
            "planned_hours_gap": planned_hours_target - Decimal(str(load.get("hours", Decimal("0")) or Decimal("0"))),
            "assignments": assignments_by_teacher.get(teacher.id, []),
            "assignment_count": len(assignments_by_teacher.get(teacher.id, [])),
            "document_count": document_count_by_teacher[teacher.id],
            "pending_document_count": pending_document_count_by_teacher[teacher.id],
            "slot_count": len(slot_items),
            "event_count": len(event_items),
            "first_events": event_items[:4],
            "has_load": bool(load.get("count") or slot_items or event_items or has_assignment),
        })

    teachers_total = len(teacher_rows)
    teacher_unassigned_count = sum(1 for item in teacher_rows if not item["has_load"])
    teacher_pending_documents = sum(item["pending_document_count"] for item in teacher_rows)

    normalized_query = (teacher_q or "").strip().casefold()
    if normalized_query:
        teacher_rows = [
            item
            for item in teacher_rows
            if normalized_query
            in " ".join(
                [
                    item["label"],
                    item["email"],
                    item["employee_code"],
                    getattr(item["teacher"].profile, "main_domain", "") or "",
                ]
            ).casefold()
        ]
    teacher_scope = teacher_scope if teacher_scope in {"all", "assigned", "unassigned", "documents_pending"} else "all"
    if teacher_scope == "assigned":
        teacher_rows = [item for item in teacher_rows if item["has_load"]]
    elif teacher_scope == "unassigned":
        teacher_rows = [item for item in teacher_rows if not item["has_load"]]
    elif teacher_scope == "documents_pending":
        teacher_rows = [item for item in teacher_rows if item["pending_document_count"]]

    return {
        "teacher_rows": teacher_rows,
        "teachers_total": teachers_total,
        "teacher_assigned_count": teachers_total - teacher_unassigned_count,
        "teacher_unassigned_count": teacher_unassigned_count,
        "teacher_pending_documents": teacher_pending_documents,
        "teacher_filtered_count": len(teacher_rows),
        "teacher_scope": teacher_scope,
    }
