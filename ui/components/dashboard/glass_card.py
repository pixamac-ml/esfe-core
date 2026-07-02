from django_components import component


@component.register("glass_card")
class GlassCard(component.Component):
    template_name = "dashboard/glass_card.html"

    def get_context_data(
        self,
        title="",
        subtitle="",
        icon="",
        gradient="blue",
        glow=True,
        tilt=True,
        **kwargs,
    ):
        gradients = {
            "blue": "from-blue-500/20 to-cyan-500/20",
            "purple": "from-purple-500/20 to-pink-500/20",
            "green": "from-emerald-500/20 to-teal-500/20",
            "orange": "from-orange-500/20 to-amber-500/20",
            "red": "from-red-500/20 to-rose-500/20",
        }
        return {
            "title": title,
            "subtitle": subtitle,
            "icon": icon,
            "gradient": gradients.get(gradient, gradients["blue"]),
            "glow": glow,
            "tilt": tilt,
            **kwargs,
        }
