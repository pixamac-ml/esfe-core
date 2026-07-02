from django_components import component


@component.register("date_picker")
class DatePicker(component.Component):
    template_name = "forms/date_picker.html"

    def get_context_data(
        self,
        name="",
        value="",
        min_date="",
        max_date="",
        errors="",
        disabled=False,
        required=False,
        class_str="",
        **kwargs,
    ):
        return {
            "name": name,
            "value": value,
            "min_date": min_date,
            "max_date": max_date,
            "errors": errors if isinstance(errors, list) else [errors] if errors else [],
            "disabled": disabled,
            "required": required,
            "class_str": class_str,
            **kwargs,
        }
