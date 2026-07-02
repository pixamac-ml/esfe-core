from django_components import component


@component.register("select")
class Select(component.Component):
    template_name = "forms/select.html"

    def get_context_data(self, name="", options=None, value="", placeholder="Choisir...", errors="", disabled=False, required=False, class_str="", **kwargs):
        return {
            "name": name,
            "options": options or [],
            "value": value,
            "placeholder": placeholder,
            "errors": errors if isinstance(errors, list) else [errors] if errors else [],
            "disabled": disabled,
            "required": required,
            "class_str": class_str,
            **kwargs,
        }
