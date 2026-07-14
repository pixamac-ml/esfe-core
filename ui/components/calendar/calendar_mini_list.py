from django_components import component


@component.register("calendar_mini_list")
class CalendarMiniList(component.Component):
    """Mini-liste de calendriers disponibles."""

    template_name = "calendar/calendar_mini_list.html"

    def get_context_data(self, calendars=None, selected_id=None, **kwargs):
        return {
            "calendars": calendars or [],
            "selected_id": selected_id,
            **kwargs,
        }
