def build_director_planning_assignment_context(
    *,
    assignments_alerts,
    class_load_items,
    teacher_load_items,
    upcoming_events,
    recent_lesson_logs,
):
    alert_tones = {
        "missing_teacher": "rose",
        "missing_location": "amber",
        "teacher_overload": "rose",
        "high_cancellation_rate": "amber",
        "unresolved_conflict": "rose",
        "class_without_events": "blue",
    }

    assignment_alert_rows = []
    for alert in assignments_alerts:
        assignment_alert_rows.append(
            {
                "message": alert.get("message") or "Alerte de planification",
                "type": (alert.get("type") or "signal").replace("_", " "),
                "level": alert.get("level") or "attention",
                "tone": alert_tones.get(alert.get("type"), "slate"),
            }
        )

    assignment_class_rows = [
        {
            "label": label,
            "count": item.get("count", 0),
            "hours": item.get("hours", 0),
        }
        for label, item in class_load_items
    ]
    assignment_teacher_rows = [
        {
            "label": label,
            "count": item.get("count", 0),
            "hours": item.get("hours", 0),
        }
        for label, item in teacher_load_items
    ]
    assignment_event_rows = []
    for event in upcoming_events[:8]:
        assignment_event_rows.append(
            {
                "title": event.get("title") or "Cours programme",
                "teacher_name": event.get("teacher_name") or "Enseignant non renseigne",
                "class_label": event.get("class_label") or "Classe non renseignee",
                "location": event.get("location") or "Salle non renseignee",
                "start_label": event.get("start_label") or event.get("date_label") or "",
                "status_label": event.get("status_label") or "",
            }
        )

    assignment_log_rows = []
    for log in recent_lesson_logs[:8]:
        assignment_log_rows.append(
            {
                "class_label": getattr(log.academic_class, "display_name", "Classe"),
                "ec_title": getattr(log.ec, "title", "EC"),
                "teacher_name": log.teacher.get_full_name() or log.teacher.username,
                "date": log.date,
                "start_time": log.start_time,
            }
        )

    return {
        "assignment_alert_rows": assignment_alert_rows,
        "assignment_class_rows": assignment_class_rows,
        "assignment_teacher_rows": assignment_teacher_rows,
        "assignment_event_rows": assignment_event_rows,
        "assignment_log_rows": assignment_log_rows,
        "assignment_critical_count": sum(1 for row in assignment_alert_rows if row["tone"] == "rose"),
        "assignment_missing_teacher_count": sum(1 for alert in assignments_alerts if alert.get("type") == "missing_teacher"),
        "assignment_missing_room_count": sum(1 for alert in assignments_alerts if alert.get("type") == "missing_location"),
        "assignment_teacher_overload_count": sum(1 for alert in assignments_alerts if alert.get("type") == "teacher_overload"),
    }
