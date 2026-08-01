from django_components import component


@component.register("ui_core.breadcrumb")
class Breadcrumb(component.Component):
    template_name = "ui_core/layout/breadcrumb.html"

    def get_context_data(self, items=None, label="Fil d'Ariane", **kwargs):
        return {"items": items or [], "label": label, **kwargs}
