from django_components import component


@component.register("ui_core.loading_overlay")
class LoadingOverlay(component.Component):
    template_name = "ui_core/feedback/loading_overlay.html"

    def get_context_data(self, loading=False, label="Chargement en cours", **kwargs):
        return {"loading": bool(loading), "label": label, **kwargs}
