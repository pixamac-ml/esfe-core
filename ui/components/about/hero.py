# components/about/hero.py

from django_components import component
from django.templatetags.static import static


@component.register("about_hero")
class AboutHero(component.Component):
    """
    Hero institutionnel pour la page À propos.

    Props :
        - label (str)
        - title (str)
        - subtitle (str)
        - image (str | None)  → chemin static ou URL media
    """

    template_name = "about/hero.html"

    def get_context_data(self, label, title, subtitle, image=None):

        # Fallback image si rien n’est fourni
        if not image:
            image = static("images/ecole.jpg")

        return {
            "label": label,
            "title": title,
            "subtitle": subtitle,
            "image": image,
        }