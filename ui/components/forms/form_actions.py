from django_components import component


@component.register("form_actions")
class FormActions(component.Component):
    template_name = "forms/form_actions.html"

    def get_context_data(self, submit_label="Enregistrer", cancel_url="", align="right", class_str="", **kwargs):
        return {
            "submit_label": submit_label,
            "cancel_url": cancel_url,
            "align": align,
            "class_str": class_str,
            **kwargs,
        }
