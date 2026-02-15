from django_components import component


@component.register("formation_hero")
class FormationHero(component.Component):
    template_name = "formation_hero/formation_hero.html"

    def get_context_data(self, programme):
        return {
            "programme": programme,
        }
