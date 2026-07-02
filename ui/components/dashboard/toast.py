from django_components import component


@component.register("toast")
class Toast(component.Component):
    template_name = "dashboard/toast.html"

    def get_context_data(
        self,
        position="top-right",
        max_toasts=3,
        dedupe_ms=2500,
        bootstrap_messages=None,
        **kwargs,
    ):
        return {
            "position": position,
            "max_toasts": max_toasts,
            "dedupe_ms": dedupe_ms,
            "bootstrap_messages": bootstrap_messages or [],
            **kwargs,
        }
