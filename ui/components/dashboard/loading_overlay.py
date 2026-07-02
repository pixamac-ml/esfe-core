from django_components import component


@component.register("loading_overlay")
class LoadingOverlay(component.Component):
    template_name = "dashboard/loading_overlay.html"

    def get_context_data(self, label="Chargement...", fullscreen=False, **kwargs):
        return {
            "label": label,
            "fullscreen": fullscreen,
            **kwargs,
        }
