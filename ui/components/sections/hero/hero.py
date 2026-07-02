import json

from django_components import component

@component.register("hero")
class Hero(component.Component):
    template_name = "sections/hero/hero.html"

    def get_context_data(
        self,
        title="École de Santé Félix Houphouët-Boigny Mali",
        subtitle="",
        image_url="",
        logo_url="",
        next_id="",
        cities=None,
    ):
        if isinstance(cities, str):
            try:
                cities = json.loads(cities)
            except (TypeError, ValueError):
                cities = []
        return {
            "title": title,
            "subtitle": subtitle,
            "image_url": image_url,
            "logo_url": logo_url,
            "next_id": next_id,
            "cities": list(cities or []),
        }
