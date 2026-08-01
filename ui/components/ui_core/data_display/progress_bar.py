from django_components import component


@component.register("ui_core.progress_bar")
class ProgressBar(component.Component):
    template_name = "ui_core/data_display/progress_bar.html"

    def get_context_data(
        self,
        value=0,
        label="Progression",
        tone="primary",
        show_value=True,
        compact=False,
        **kwargs,
    ):
        try:
            value = min(max(float(value), 0), 100)
        except (TypeError, ValueError):
            value = 0
        tones = {"neutral", "primary", "info", "success", "warning", "danger"}
        return {
            "value": int(value) if value.is_integer() else value,
            "label": label,
            "tone": tone if tone in tones else "neutral",
            "show_value": bool(show_value),
            "compact": bool(compact),
            **kwargs,
        }
