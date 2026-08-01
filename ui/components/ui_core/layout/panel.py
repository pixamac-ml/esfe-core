from django_components import component


@component.register("ui_core.panel")
class Panel(component.Component):
    template_name = "ui_core/layout/panel.html"

    def get_context_data(
        self,
        title="",
        subtitle="",
        padding=True,
        density="comfortable",
        tone="neutral",
        collapsible=False,
        open=True,
        loading=False,
        error="",
        scrollable=False,
        **kwargs,
    ):
        return {
            "title": title,
            "subtitle": subtitle,
            "padding": bool(padding),
            "density": density if density in {"comfortable", "compact"} else "comfortable",
            "tone": tone if tone in {"neutral", "primary", "info", "success", "warning", "danger"} else "neutral",
            "collapsible": bool(collapsible),
            "open": bool(open),
            "loading": bool(loading),
            "error": error,
            "scrollable": bool(scrollable),
            **kwargs,
        }
