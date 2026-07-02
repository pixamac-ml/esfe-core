from django_components import component


@component.register("stepper")
class Stepper(component.Component):
    template_name = "forms/stepper.html"

    def get_context_data(
        self,
        steps=None,
        active_step=0,
        size="md",
        variant="horizontal",
        **kwargs,
    ):
        sizes = {
            "sm": {"circle": "w-6 h-6 text-[10px]", "icon": "w-3 h-3", "label": "text-[10px]", "connector": "w-8"},
            "md": {"circle": "w-8 h-8 text-xs", "icon": "w-3.5 h-3.5", "label": "text-xs", "connector": "w-12"},
            "lg": {"circle": "w-10 h-10 text-sm", "icon": "w-4 h-4", "label": "text-sm", "connector": "w-16"},
        }
        return {
            "steps": steps or [],
            "active_step": active_step,
            "size": size,
            "size_map": sizes.get(size, sizes["md"]),
            "variant": variant,
            **kwargs,
        }
