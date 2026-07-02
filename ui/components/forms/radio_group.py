from django_components import component


@component.register("radio_group")
class RadioGroup(component.Component):
    template_name = "forms/radio_group.html"

    def get_context_data(self, name="", options=None, value="", errors="", disabled=False, required=False, class_str="", **kwargs):
        return {
            "name": name,
            "options": options or [],
            "value": value,
            "errors": errors if isinstance(errors, list) else [errors] if errors else [],
            "disabled": disabled,
            "required": required,
            "class_str": class_str,
            **kwargs,
        }
