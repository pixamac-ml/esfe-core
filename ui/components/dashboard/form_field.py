from django_components import component


@component.register("form_field")
class FormField(component.Component):
    template_name = "dashboard/form_field.html"

    def get_context_data(
        self,
        label="",
        name="",
        value="",
        errors="",
        required=False,
        disabled=False,
        type="text",
        placeholder="",
        help_text="",
        class_str="",
        hx_get="",
        hx_post="",
        hx_trigger="blur change",
        hx_target="",
        hx_swap="outerHTML",
        **kwargs,
    ):
        return {
            "label": label,
            "name": name,
            "value": value,
            "errors": errors if isinstance(errors, list) else [errors] if errors else [],
            "required": required,
            "disabled": disabled,
            "type": type,
            "placeholder": placeholder,
            "help_text": help_text,
            "class_str": class_str,
            "hx_get": hx_get,
            "hx_post": hx_post,
            "hx_trigger": hx_trigger,
            "hx_target": hx_target or f"#form-field-{name}-errors",
            "hx_swap": hx_swap,
            **kwargs,
        }
