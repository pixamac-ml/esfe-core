from django_components import component


@component.register("breadcrumb")
class Breadcrumb(component.Component):
    template_name = "layout/breadcrumb.html"

    def get_context_data(self, items=None, **kwargs):
        return {
            "items": items or [],
            **kwargs,
        }
