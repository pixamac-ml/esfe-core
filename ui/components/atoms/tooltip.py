from django_components import component


@component.register("tooltip")
class Tooltip(component.Component):
    template_name = "atoms/tooltip.html"

    def get_context_data(self, text="", position="top", **kwargs):
        positions = {
            "top": "bottom-full left-1/2 -translate-x-1/2 mb-2",
            "bottom": "top-full left-1/2 -translate-x-1/2 mt-2",
            "left": "right-full top-1/2 -translate-y-1/2 mr-2",
            "right": "left-full top-1/2 -translate-y-1/2 ml-2",
        }
        arrows = {
            "top": "top-full left-1/2 -translate-x-1/2 border-l-[6px] border-r-[6px] border-t-[6px] border-l-transparent border-r-transparent border-t-[color:var(--text)]",
            "bottom": "bottom-full left-1/2 -translate-x-1/2 border-l-[6px] border-r-[6px] border-b-[6px] border-l-transparent border-r-transparent border-b-[color:var(--text)]",
            "left": "left-full top-1/2 -translate-y-1/2 border-t-[6px] border-b-[6px] border-l-[6px] border-t-transparent border-b-transparent border-l-[color:var(--text)]",
            "right": "right-full top-1/2 -translate-y-1/2 border-t-[6px] border-b-[6px] border-r-[6px] border-t-transparent border-b-transparent border-r-[color:var(--text)]",
        }
        return {
            "text": text,
            "position": position,
            "position_class": positions.get(position, positions["top"]),
            "arrow_class": arrows.get(position, arrows["top"]),
            **kwargs,
        }
