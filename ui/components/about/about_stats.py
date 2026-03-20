# ui/components/about/about_stats.py

from django_components import component


@component.register("about_stats")
class AboutStats(component.Component):
    """
    Section statistiques avec compteurs animés.
    """

    template_name = "about/about_stats.html"

    def get_context_data(self, stats=None):
        return {
            "stats": stats or [],
        }