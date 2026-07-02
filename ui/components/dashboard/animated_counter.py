from django_components import component


@component.register("animated_counter")
class AnimatedCounter(component.Component):
    template_name = "dashboard/animated_counter.html"

    def get_context_data(
        self,
        value=0,
        label="",
        icon="",
        color="blue",
        duration=2000,
        prefix="",
        suffix="",
        **kwargs,
    ):
        colors = {
            "blue": "from-blue-500 to-cyan-500",
            "green": "from-emerald-500 to-teal-500",
            "purple": "from-purple-500 to-pink-500",
            "orange": "from-orange-500 to-amber-500",
            "red": "from-red-500 to-rose-500",
        }
        return {
            "value": value,
            "label": label,
            "icon": icon,
            "color": colors.get(color, colors["blue"]),
            "duration": duration,
            "prefix": prefix,
            "suffix": suffix,
            **kwargs,
        }
