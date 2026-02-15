from django_components import component


@component.register("formation_trust_block")
class FormationTrustBlock(component.Component):
    template_name = "formation_trust_block/formation_trust_block.html"

    def get_context_data(self):
        return {}
