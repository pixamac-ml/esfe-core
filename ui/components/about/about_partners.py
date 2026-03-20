# ui/components/about/about_partners.py

from django_components import component


@component.register("about_partners")
class AboutPartners(component.Component):
    """
    Section partenaires avec logos.
    """

    template_name = "about/about_partners.html"

    def get_context_data(
        self,
        partners=None,
        title="Nos Partenaires",
        subtitle="",
    ):
        return {
            "partners": partners or [],
            "title": title,
            "subtitle": subtitle,
        }