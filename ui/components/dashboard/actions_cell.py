from django_components import component


@component.register("actions_cell")
class ActionsCell(component.Component):
    template_name = "dashboard/actions_cell.html"

    def get_context_data(self, actions=None, **kwargs):
        return {
            "actions": actions or [],
            **kwargs,
        }
