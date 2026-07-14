from django_components import component


@component.register("academic_page_layout")
class AcademicPageLayout(component.Component):
    """Gabarit de page scolaire : header + grille + slots."""

    template_name = "academic/academic_page_layout.html"

    def get_context_data(
        self,
        title="",
        subtitle="",
        kicker="",
        breadcrumb_items=None,
        class_str="",
        **kwargs,
    ):
        return {
            "title": title,
            "subtitle": subtitle,
            "kicker": kicker,
            "breadcrumb_items": breadcrumb_items or [],
            "class_str": class_str,
            **kwargs,
        }
