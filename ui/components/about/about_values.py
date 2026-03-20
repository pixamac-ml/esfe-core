# ui/components/about/about_values.py

from django_components import component


@component.register("about_values")
class AboutValues(component.Component):
    """
    Section valeurs avec cartes animées.
    """

    template_name = "about/about_values.html"

    def get_context_data(self, values=None, title="Nos Valeurs", subtitle=""):
        return {
            "values": values or [],
            "title": title,
            "subtitle": subtitle,
        }