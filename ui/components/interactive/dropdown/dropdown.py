from django_components import component


@component.register("dropdown")
class Dropdown(component.Component):
    template_name = "interactive/dropdown/dropdown.html"

    def get_context_data(self, items=None, position="bottom-right", **kwargs):
        positions = {
            "bottom-left": "left-0",
            "bottom-right": "right-0",
            "top-left": "bottom-full left-0 mb-1",
            "top-right": "bottom-full right-0 mb-1",
        }
        return {
            "items": items or [],
            "position_class": positions.get(position, positions["bottom-right"]),
            **kwargs,
        }
