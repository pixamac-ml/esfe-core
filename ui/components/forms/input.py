from django_components import component


@component.register("input")
class Input(component.Component):
    template_name = "forms/input.html"

    def get_context_data(self, name="", value="", type="text", placeholder="", errors="", disabled=False, required=False, class_str="", **kwargs):
        return {
            "name": name,
            "value": value,
            "type": type,
            "placeholder": placeholder,
            "errors": errors if isinstance(errors, list) else [errors] if errors else [],
            "disabled": disabled,
            "required": required,
            "class_str": class_str,
            **kwargs,
        }
