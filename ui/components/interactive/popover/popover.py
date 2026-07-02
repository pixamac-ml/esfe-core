from django_components import component


@component.register("popover")
class Popover(component.Component):
    template_name = "interactive/popover/popover.html"

    def get_context_data(
        self,
        title="",
        position="bottom",
        width="auto",
        trigger_class="",
        **kwargs,
    ):
        positions = {
            "top": "bottom-full left-1/2 -translate-x-1/2 mb-2",
            "bottom": "top-full left-1/2 -translate-x-1/2 mt-2",
            "left": "right-full top-1/2 -translate-y-1/2 mr-2",
            "right": "left-full top-1/2 -translate-y-1/2 ml-2",
        }
        widths = {
            "auto": "w-auto",
            "sm": "w-48",
            "md": "w-64",
            "lg": "w-80",
            "xl": "w-96",
            "full": "w-screen max-w-md",
        }
        return {
            "title": title,
            "position": position,
            "position_class": positions.get(position, positions["bottom"]),
            "width_class": widths.get(width, widths["auto"]),
            "trigger_class": trigger_class,
            **kwargs,
        }
