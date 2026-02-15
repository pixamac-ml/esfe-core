from django_components import component


@component.register("formation_overview")
class FormationOverview(component.Component):
    template_name = "formation_overview/formation_overview.html"

    def get_context_data(self, programme):
        return {
            "programme": programme,
        }
