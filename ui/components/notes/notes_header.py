from django_components import component


@component.register("notes_header")
class NotesHeader(component.Component):
    template_name = "notes/notes_header.html"

    def get_context_data(self, academic_class, semester, rows, active_session_label, workflow_badge):
        return {
            "academic_class": academic_class,
            "semester": semester,
            "rows": rows,
            "active_session_label": active_session_label,
            "workflow_badge": workflow_badge,
        }
