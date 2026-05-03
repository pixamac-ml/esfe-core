from django_components import component


@component.register("notes_actions_bar")
class NotesActionsBar(component.Component):
    template_name = "notes/notes_actions_bar.html"

    def get_context_data(self, academic_class, semester, active_session_type, workflow_permissions, first_enrollment, publish_ready, embedded_in_dashboard=False):
        return {
            "academic_class": academic_class,
            "semester": semester,
            "active_session_type": active_session_type,
            "workflow_permissions": workflow_permissions,
            "first_enrollment": first_enrollment,
            "publish_ready": publish_ready,
            "embedded_in_dashboard": embedded_in_dashboard,
        }
