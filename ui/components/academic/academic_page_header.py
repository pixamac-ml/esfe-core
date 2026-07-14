from django_components import component


@component.register("academic_page_header")
class AcademicPageHeader(component.Component):
    """En-tête de page scolaire : titre, sous-titre, breadcrumb, actions."""

    template_name = "academic/academic_page_header.html"

    def get_context_data(
        self,
        title="",
        subtitle="",
        breadcrumb_items=None,
        kicker="",
        class_str="",
        **kwargs,
    ):
        return {
            "title": title,
            "subtitle": subtitle,
            "breadcrumb_items": breadcrumb_items or [],
            "kicker": kicker,
            "class_str": class_str,
            **kwargs,
        }
