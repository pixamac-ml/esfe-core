from django_components import component


@component.register("activity_wave")
class ActivityWave(component.Component):
    template_name = "dashboard/activity_wave.html"

    def get_context_data(
        self,
        data=None,
        color_blue="blue",
        color_purple="purple",
        height=120,
        **kwargs,
    ):
        return {
            "data": data or [],
            "color_blue": color_blue,
            "color_purple": color_purple,
            "height": height,
            "bars": range(20),
            **kwargs,
        }
