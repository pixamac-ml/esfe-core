from django_components import component


@component.register("form_field")
class FormField(component.Component):
    template_name = "dashboard/form_field.html"

    def get_context_data(self, label="", name="", value="", errors="", required=False, type="text", placeholder="", help_text="", **kwargs):
        return {
            "label": label,
            "name": name,
            "value": value,
            "errors": errors if isinstance(errors, list) else [errors] if errors else [],
            "required": required,
            "type": type,
            "placeholder": placeholder,
            "help_text": help_text,
            **kwargs,
        }
