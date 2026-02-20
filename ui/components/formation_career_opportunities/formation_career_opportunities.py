from django_components import component


@component.register("formation_career_opportunities")
class FormationCareerOpportunities(component.Component):
    template_name = "formation_career_opportunities/formation_career_opportunities.html"

    def get_context_data(self, career_opportunities: str):

        items = []

        if career_opportunities:
            items = [
                line.strip()
                for line in career_opportunities.splitlines()
                if line.strip()
            ]

        return {
            "items": items
        }