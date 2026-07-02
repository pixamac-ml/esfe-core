from django_components import component


@component.register("amount_input")
class AmountInput(component.Component):
    template_name = "forms/amount_input.html"

    def get_context_data(self, name="", value="", currency="FCFA", placeholder="0", errors="", disabled=False, required=False, class_str="", **kwargs):
        return {
            "name": name,
            "value": value,
            "currency": currency,
            "placeholder": placeholder,
            "errors": errors if isinstance(errors, list) else [errors] if errors else [],
            "disabled": disabled,
            "required": required,
            "class_str": class_str,
            **kwargs,
        }
