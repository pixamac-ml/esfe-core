from django_components import component


@component.register("calendar_entry_card")
class CalendarEntryCard(component.Component):
    """Carte récapitulative d'une entrée de calendrier."""

    template_name = "calendar/calendar_entry_card.html"

    def get_context_data(self, entry=None, show_actions=True, **kwargs):
        return {
            "entry": entry or {},
            "show_actions": show_actions,
            **kwargs,
        }
