from django_components import component


@component.register("notes_grid")
class NotesGrid(component.Component):
    template_name = "notes/notes_table.html"

    def get_context_data(self, academic_class, semester, state):
        return {
            "academic_class": academic_class,
            "semester": semester,
            "state": state,
        }
