from django_components import component


@component.register("notes_actions")
class NotesActions(component.Component):
    template_name = "notes/notes_actions.html"

    def get_context_data(self, actions, academic_class, semester):
        return {
            "actions": actions,
            "academic_class": academic_class,
            "semester": semester,
        }
