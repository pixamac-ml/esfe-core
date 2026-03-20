# ui/components/about/about_branches.py

from django_components import component


@component.register("about_branches")
class AboutBranches(component.Component):
    """
    Section annexes/implantations.
    """

    template_name = "about/about_branches.html"

    def get_context_data(
        self,
        branches=None,
        title="Nos Implantations",
        subtitle="",
    ):
        return {
            "branches": branches or [],
            "title": title,
            "subtitle": subtitle,
        }