# ui/components/about/about_hero.py

from django_components import component
from django.templatetags.static import static


@component.register("about_hero")
class AboutHero(component.Component):
    """
    Hero plein écran avec animations d'entrée et effet parallax.
    """

    template_name = "about/about_hero.html"

    def get_context_data(
        self,
        title="Notre Institution",
        subtitle="",
        label="À propos",
        image=None,
        cta_text=None,
        cta_url=None,
    ):
        if not image:
            image = static("images/hero-default.jpg")

        return {
            "title": title,
            "subtitle": subtitle,
            "label": label,
            "image": image if image else None,  # Gère le cas vide
            "cta_text": cta_text,
            "cta_url": cta_url,
        }