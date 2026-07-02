from django_components import component


@component.register("schedule")
class Schedule(component.Component):
    template_name = "dashboard/schedule.html"

    DAY_LABELS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam"]

    def get_context_data(
        self,
        slots=None,
        time_slots=None,
        days=None,
        week_label="",
        **kwargs,
    ):
        time_slots = time_slots or [
            "07h", "08h", "09h", "10h", "11h",
            "12h", "13h", "14h", "15h", "16h", "17h", "18h",
        ]
        days = days or self.DAY_LABELS

        processed = []
        for raw in (slots or []):
            day = int(raw.get("day", 0) or 0)
            start = int(raw.get("start", 0) or 0)
            end = int(raw.get("end") or raw.get("start", 0) or 0) + 1
            if end <= start:
                end = start + 1
            col = day + 2
            start_row = start + 2
            span = end - start
            color = raw.get("color", "school-primary")
            processed.append({
                "label": raw.get("label", ""),
                "teacher": raw.get("teacher", ""),
                "room": raw.get("room", ""),
                "style": (
                    f"grid-column: {col}; grid-row: {start_row} / span {span};"
                    f"background: var(--{color}-soft);"
                    f"border-color: var(--{color})/30;"
                ),
                "color_var": f"var(--{color})",
            })

        return {
            "processed_slots": processed,
            "time_slots": time_slots,
            "days": days,
            "week_label": week_label,
            "num_days": len(days),
            **kwargs,
        }
