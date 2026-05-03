from django_components import component


@component.register("notes_anomaly_panel")
class NotesAnomalyPanel(component.Component):
    template_name = "notes/notes_anomaly_panel.html"

    def get_context_data(self, state):
        return {"state": state}
