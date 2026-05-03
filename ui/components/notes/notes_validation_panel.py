from django_components import component


@component.register("notes_validation_panel")
class NotesValidationPanel(component.Component):
    template_name = "notes/notes_validation_panel.html"

    def get_context_data(self, state):
        return {"state": state}
