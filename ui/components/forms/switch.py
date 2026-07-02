from django_components import component


@component.register("switch")
class Switch(component.Component):
    template_name = "forms/switch.html"

    def get_context_data(self, name="", label="", checked=False, value="on", disabled=False, required=False, class_str="", **kwargs):
        return {
            "name": name,
            "label": label,
            "checked": checked,
            "value": value,
            "disabled": disabled,
            "required": required,
            "class_str": class_str,
            **kwargs,
        }
