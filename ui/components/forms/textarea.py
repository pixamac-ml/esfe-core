from django_components import component


@component.register("textarea")
class Textarea(component.Component):
    template_name = "forms/textarea.html"

    def get_context_data(self, name="", value="", placeholder="", rows=4, errors="", disabled=False, required=False, class_str="", **kwargs):
        return {
            "name": name,
            "value": value,
            "placeholder": placeholder,
            "rows": rows,
            "errors": errors if isinstance(errors, list) else [errors] if errors else [],
            "disabled": disabled,
            "required": required,
            "class_str": class_str,
            **kwargs,
        }
