# ui/components/about/about_infrastructure.py

from django_components import component


@component.register("about_infrastructure")
class AboutInfrastructure(component.Component):
    """
    Galerie des infrastructures.
    """

    template_name = "about/about_infrastructure.html"

    def get_context_data(
        self,
        infrastructures=None,
        title="Nos Infrastructures",
        subtitle="",
    ):
        return {
            "infrastructures": infrastructures or [],
            "title": title,
            "subtitle": subtitle,
        }