from django_components import component


@component.register("badge")
class Badge(component.Component):
    template_name = "atoms/badge.html"

    def get_context_data(
        self,
        label="",
        tone="neutral",
        size="md",
        icon="",
        dot=False,
        dismissible=False,
        pulse=False,
        clickable=False,
        class_str="",
        **kwargs,
    ):
        sizes = {
            "sm": "px-2 py-0.5 text-[10px]",
            "md": "px-3 py-1 text-[11px]",
            "lg": "px-4 py-1.5 text-xs",
        }
        return {
            "label": label,
            "tone": tone,
            "size": size,
            "size_class": sizes.get(size, sizes["md"]),
            "icon": icon,
            "dot": dot,
            "dismissible": dismissible,
            "pulse": pulse,
            "clickable": clickable,
            "class_str": class_str,
            **kwargs,
        }
