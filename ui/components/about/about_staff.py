# ui/components/about/about_staff.py

from django_components import component


@component.register("about_staff")
class AboutStaff(component.Component):
    """
    Section équipe/personnel.
    """

    template_name = "about/about_staff.html"

    def get_context_data(
        self,
        direction=None,
        teachers=None,
        title="Notre Équipe",
        subtitle="",
    ):
        return {
            "direction": direction or [],
            "teachers": teachers or [],
            "title": title,
            "subtitle": subtitle,
        }