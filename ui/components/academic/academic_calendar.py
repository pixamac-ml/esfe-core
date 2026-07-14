from django_components import component


@component.register("academic_calendar")
class AcademicCalendar(component.Component):
    """Calendrier scolaire / emploi du temps, wrapper autour de schedule."""

    template_name = "academic/academic_calendar.html"

    def get_context_data(
        self,
        slots=None,
        time_slots=None,
        days=None,
        week_label="",
        title="Emploi du temps",
        icon="calendar",
        **kwargs,
    ):
        return {
            "slots": slots or [],
            "time_slots": time_slots,
            "days": days,
            "week_label": week_label,
            "title": title,
            "icon": icon,
            **kwargs,
        }
