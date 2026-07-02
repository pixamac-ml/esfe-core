import json

from django.core.serializers.json import DjangoJSONEncoder
from django_components import component


@component.register("combobox")
class Combobox(component.Component):
    template_name = "forms/combobox.html"

    def get_context_data(
        self,
        name="",
        options=None,
        value="",
        placeholder="Rechercher...",
        errors="",
        disabled=False,
        required=False,
        class_str="",
        **kwargs,
    ):
        normalized_options = list(options or [])
        return {
            "name": name,
            "options": normalized_options,
            "options_json": json.dumps(normalized_options, cls=DjangoJSONEncoder),
            "value": value,
            "placeholder": placeholder,
            "errors": errors if isinstance(errors, list) else [errors] if errors else [],
            "disabled": disabled,
            "required": required,
            "class_str": class_str,
            **kwargs,
        }
