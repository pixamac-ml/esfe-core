from django_components import component


WORKFLOW_STEPS = [
    {"key": "EMPTY", "label": "Vide", "icon": "circle", "order": 0},
    {"key": "INPUT", "label": "Saisie", "icon": "edit-3", "order": 1},
    {"key": "CALCUL", "label": "Calculé", "icon": "calculator", "order": 2},
    {"key": "REVIEW", "label": "Relecture", "icon": "eye", "order": 3},
    {"key": "CORRECT", "label": "Correction", "icon": "edit", "order": 4},
    {"key": "FINAL", "label": "Final", "icon": "check-circle", "order": 5},
    {"key": "PUBLISHED", "label": "Publié", "icon": "shield-check", "order": 6},
]


STATUS_TO_STEP = {
    "empty": "EMPTY",
    "in_progress": "INPUT",
    "ready_to_publish_normal": "CALCUL",
    "normal_published": "REVIEW",
    "retake_in_progress": "CORRECT",
    "ready_to_publish_final": "FINAL",
    "final_published": "PUBLISHED",
}

STATUS_COLORS = {
    "EMPTY": "slate",
    "INPUT": "blue",
    "CALCUL": "amber",
    "REVIEW": "violet",
    "CORRECT": "orange",
    "FINAL": "emerald",
    "PUBLISHED": "emerald",
}


def map_state_to_step(state_code):
    return STATUS_TO_STEP.get(state_code, "EMPTY")


RETAKE_STEPS = {"CORRECT", "FINAL", "PUBLISHED"}


def build_workflow_bar_data(state_code, has_candidates=None):
    current_step_key = map_state_to_step(state_code)
    current_order = next((s["order"] for s in WORKFLOW_STEPS if s["key"] == current_step_key), 0)

    no_retake_needed = has_candidates is False and current_order > 2

    steps = []
    for step in WORKFLOW_STEPS:
        is_active = step["order"] <= current_order
        is_current = step["key"] == current_step_key
        color = STATUS_COLORS.get(step["key"], "slate")
        steps.append({
            "key": step["key"],
            "label": step["label"],
            "icon": step["icon"],
            "order": step["order"],
            "active": is_active,
            "current": is_current,
            "color": color,
        })

    total = len(WORKFLOW_STEPS)
    progress_pct = round((current_order / (total - 1)) * 100) if total > 1 else 0

    next_step = None
    for s in WORKFLOW_STEPS:
        if s["order"] == current_order + 1:
            next_step = s["label"]
            break

    return {
        "steps": steps,
        "current_key": current_step_key,
        "current_label": next((s["label"] for s in WORKFLOW_STEPS if s["key"] == current_step_key), "Inconnu"),
        "next_step_label": next_step,
        "total_steps": total,
        "current_position": current_order + 1,
        "progress_pct": progress_pct,
        "no_retake_needed": no_retake_needed,
    }


@component.register("notes_workflow_bar")
class NotesWorkflowBar(component.Component):
    template_name = "notes/notes_workflow_bar.html"

    def get_context_data(self, state_code="empty", has_candidates=None, **kwargs):
        return build_workflow_bar_data(state_code, has_candidates=has_candidates)
