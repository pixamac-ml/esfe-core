from django_components import component


@component.register("notes_state")
class NotesState(component.Component):
    template_name = "notes/notes_state_banner.html"

    def get_context_data(self, state):
        return {"state": state}
