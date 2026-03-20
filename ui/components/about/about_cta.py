# ui/components/about/about_cta.py

from django_components import component


@component.register("about_cta")
class AboutCTA(component.Component):
    """
    Section CTA finale.
    """

    template_name = "about/about_cta.html"

    def get_context_data(
        self,
        title="Rejoignez-nous",
        subtitle="",
        button_text="Candidater",
        button_url="/candidature/",
        secondary_text=None,
        secondary_url=None,
    ):
        return {
            "title": title,
            "subtitle": subtitle,
            "button_text": button_text,
            "button_url": button_url,
            "secondary_text": secondary_text,
            "secondary_url": secondary_url,
        }