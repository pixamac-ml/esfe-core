def build_director_classroom_ops_context(
    *,
    class_cards,
    selected_class,
    selected_class_rows,
    selected_class_student_count,
    selected_class_schedule,
):
    operation_class_rows = []
    for item in class_cards:
        row_schedule = selected_class_schedule if selected_class and item["class"].id == selected_class.id else None
        summary = (row_schedule or {}).get("summary", {}) if row_schedule else {}
        operation_class_rows.append(
            {
                "class": item["class"],
                "label": item["class"].display_name,
                "student_count": item["student_count"],
                "semester_count": item["semester_count"],
                "progress": item["progress"],
                "ready_to_validate_count": item["ready_to_validate_count"],
                "ready_to_publish_count": item["ready_to_publish_count"],
                "published_count": item["published_count"],
                "workflow_bucket": item["workflow_bucket"],
                "planned_count": summary.get("planned", 0),
                "completed_count": summary.get("completed", 0),
                "cancelled_count": summary.get("cancelled", 0),
            }
        )

    selected_operation_class = None
    if selected_class is not None:
        schedule_summary = (selected_class_schedule or {}).get("summary", {}) if selected_class_schedule else {}
        selected_operation_class = {
            "class": selected_class,
            "label": selected_class.display_name,
            "student_count": selected_class_student_count,
            "semester_count": len(selected_class_rows),
            "planned_count": schedule_summary.get("planned", 0),
            "completed_count": schedule_summary.get("completed", 0),
            "cancelled_count": schedule_summary.get("cancelled", 0),
            "pending_count": max(schedule_summary.get("planned", 0) - schedule_summary.get("completed", 0), 0),
            "semester_rows": selected_class_rows[:6],
            "weekly_events": ((selected_class_schedule or {}).get("events") or [])[:8],
        }

    return {
        "operation_class_rows": operation_class_rows,
        "selected_operation_class": selected_operation_class,
    }
