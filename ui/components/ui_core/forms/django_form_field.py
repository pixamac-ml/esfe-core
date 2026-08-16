from django_components import component


@component.register("ui_core.django_form_field")
class DjangoFormField(component.Component):
    """Render a Django BoundField with the certified UI Core field contract."""

    template_name = "ui_core/forms/django_form_field.html"

    def get_context_data(self, field=None, **kwargs):
        widget = getattr(getattr(field, "field", None), "widget", None)
        widget_name = widget.__class__.__name__ if widget else ""
        return {
            "field": field,
            "is_checkbox": widget_name == "CheckboxInput",
            "is_wide": widget_name in {
                "Textarea",
                "ClearableFileInput",
                "FileInput",
                "SelectMultiple",
                "CheckboxInput",
            },
            **kwargs,
        }
