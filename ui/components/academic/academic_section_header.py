from django_components import component


@component.register("academic_section_header")
class AcademicSectionHeader(component.Component):
    """En-tête de section scolaire : titre, sous-titre, icône, action."""

    template_name = "academic/academic_section_header.html"

    def get_context_data(
        self,
        title="",
        subtitle="",
        icon="",
        align="left",
        badge="",
        **kwargs,
    ):
        return {
            "title": title,
            "subtitle": subtitle,
            "icon": icon,
            "align": align,
            "badge": badge,
            **kwargs,
        }
