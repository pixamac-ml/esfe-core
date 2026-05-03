from django_components import component


@component.register("notes_workflow")
class NotesWorkflow(component.Component):
    template_name = "notes/notes_workflow.html"

    def get_context_data(self, academic_class, semester, state, actions):
        return {
            "academic_class": academic_class,
            "semester": semester,
            "state": state,
            "actions": actions,
        }
