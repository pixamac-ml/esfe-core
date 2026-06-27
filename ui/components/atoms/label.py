from django_components import component


@component.register("label")
class Label(component.Component):
    template_name = "atoms/label.html"

    def get_context_data(self, text="", for_id="", required=False, **kwargs):
        return {
            "text": text,
            "for_id": for_id,
            "required": required,
            **kwargs,
        }
