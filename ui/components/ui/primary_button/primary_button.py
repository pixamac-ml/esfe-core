from django_components import component


@component.register("primary_button")
class PrimaryButton(component.Component):
    template_name = "components/ui/button/primary_button.html"

    def get_context_data(self, label, type="button", full_width=False):
        return {
            "label": label,
            "type": type,
            "full_width": full_width,
        }
