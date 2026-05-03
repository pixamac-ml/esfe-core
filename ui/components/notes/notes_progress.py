from django_components import component


@component.register("notes_progress")
class NotesProgress(component.Component):
    template_name = "notes/notes_progress.html"

    def get_context_data(self, state):
        return {"state": state}
