from django_components import component


@component.register("toast")
class Toast(component.Component):
    template_name = "dashboard/toast.html"

    def get_context_data(self, **kwargs):
        return {}
