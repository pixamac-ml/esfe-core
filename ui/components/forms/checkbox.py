from django_components import component


@component.register("checkbox")
class Checkbox(component.Component):
    template_name = "forms/checkbox.html"

    def get_context_data(self, name="", label="", checked=False, value="on", errors="", disabled=False, required=False, class_str="", **kwargs):
        return {
            "name": name,
            "label": label,
            "checked": checked,
            "value": value,
            "errors": errors if isinstance(errors, list) else [errors] if errors else [],
            "disabled": disabled,
            "required": required,
            "class_str": class_str,
            **kwargs,
        }
