from django_components import component


@component.register("calendar_month_grid")
class CalendarMonthGrid(component.Component):
    """Grille mensuelle d'événements du calendrier académique."""

    template_name = "calendar/calendar_month_grid.html"

    def get_context_data(
        self,
        year=2026,
        month=1,
        entries=None,
        empty_message="Aucun événement ce mois-ci",
        **kwargs,
    ):
        entries = entries or []
        return {
            "year": year,
            "month": month,
            "entries": entries,
            "empty_message": empty_message,
            "day_headers": ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"],
            **kwargs,
        }
