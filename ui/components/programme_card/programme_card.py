from django_components import component


@component.register("programme_card")
class ProgrammeCard(component.Component):
    template_name = "programme_card/programme_card.html"

    def get_context_data(
        self,
        title,
        short_description,
        cycle,
        duration,
        url,
        diploma=None,
        is_featured=False,
    ):
        return {
            "title": title,
            "short_description": short_description,
            "cycle": cycle,
            "duration": duration,
            "url": url,
            "diploma": diploma,
            "is_featured": is_featured,
        }
