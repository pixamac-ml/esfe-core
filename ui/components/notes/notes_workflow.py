from django_components import component

from ui.components.notes.notes_workflow_bar import build_workflow_bar_data


@component.register("notes_workflow")
class NotesWorkflow(component.Component):
    template_name = "notes/notes_workflow.html"

    def get_context_data(self, academic_class, semester, state, actions, drawer_mode=False):
        has_candidates = bool(state.retake_candidates_count) if state else None
        workflow_bar = build_workflow_bar_data(state.code if state else "empty", has_candidates=has_candidates)
        return {
            "academic_class": academic_class,
            "semester": semester,
            "state": state,
            "actions": actions,
            "drawer_mode": drawer_mode,
            "workflow_bar": workflow_bar,
        }
