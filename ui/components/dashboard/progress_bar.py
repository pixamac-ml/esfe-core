from django_components import component


@component.register("progress_bar")
class ProgressBar(component.Component):
    template_name = "dashboard/progress_bar.html"

    def get_context_data(self, label="", value=0, max_value=100, **kwargs):
        try:
            normalized_value = int(value)
        except (TypeError, ValueError):
            normalized_value = 0
        normalized_value = max(0, min(normalized_value, int(max_value or 100)))
        return {
            "label": label,
            "value": normalized_value,
            "max_value": max_value or 100,
            **kwargs,
        }

