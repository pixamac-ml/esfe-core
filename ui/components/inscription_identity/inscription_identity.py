from django_components import component


@component.register("inscription_identity")
class InscriptionIdentity(component.Component):
    template_name = "inscription_identity/inscription_identity.html"

    def get_context_data(self, candidature, programme):
        return {
            "candidature": candidature,
            "programme": programme,
        }
