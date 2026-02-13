from django_components import component

@component.register("hero")
class Hero(component.Component):
    template_name = "sections/hero/hero.html"

    def get_context_data(
        self,
        title="ESFE",
        subtitle="",
        image_url="",
        next_id="",
        cities="[]",
    ):
        return {
            "title": title,
            "subtitle": subtitle,
            "image_url": image_url,
            "next_id": next_id,
            "cities": cities,
        }
