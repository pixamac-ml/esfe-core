from django_components import component


@component.register("info_field")
class InfoField(component.Component):
    template_name = "dashboard/info_field.html"

    def get_context_data(self, label="", value="", extra_class="", **kwargs):
        return {
            "label": label,
            "value": value,
            "extra_class": extra_class,
            **kwargs,
        }

