from django_components import component


@component.register("inscription_status")
class InscriptionStatus(component.Component):
    template_name = "inscription_status/inscription_status.html"

    def get_context_data(self, inscription):
        return {
            "inscription": inscription
        }
