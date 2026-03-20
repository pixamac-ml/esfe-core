# ui/components/about/about_formations.py

from django_components import component


@component.register("about_formations")
class AboutFormations(component.Component):
    """
    Aperçu des formations proposées.
    """

    template_name = "about/about_formations.html"

    def get_context_data(
        self,
        programmes=None,
        title="Nos Formations",
        subtitle="",
        cta_text="Voir toutes les formations",
        cta_url="/formations/",
    ):
        return {
            "programmes": programmes or [],
            "title": title,
            "subtitle": subtitle,
            "cta_text": cta_text,
            "cta_url": cta_url,
        }