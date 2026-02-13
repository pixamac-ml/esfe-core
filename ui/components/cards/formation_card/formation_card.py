from django_components import component

@component.register("formation_card")
class FormationCard(component.Component):
    template_name = "cards/formation_card/formation_card.html"

    def get_context_data(self, title, description, duration, href):
        return {
            "title": title,
            "description": description,
            "duration": duration,
            "href": href,
        }
