from django_components import component


@component.register("calendar_year_grid")
class CalendarYearGrid(component.Component):
    """Vue annuelle condensée du calendrier académique."""

    template_name = "calendar/calendar_year_grid.html"

    def get_context_data(self, year=2026, months=None, **kwargs):
        return {
            "year": year,
            "months": months or [],
            **kwargs,
        }
