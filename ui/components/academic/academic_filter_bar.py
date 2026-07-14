from django_components import component


@component.register("academic_filter_bar")
class AcademicFilterBar(component.Component):
    """Barre de filtres scolaire HTMX pour tableaux et listes."""

    template_name = "academic/academic_filter_bar.html"

    def get_context_data(
        self,
        filters=None,
        id="academic-filter-bar",
        hx_target="#academic-table",
        class_str="",
        **kwargs,
    ):
        return {
            "filters": filters or [],
            "id": id,
            "hx_target": hx_target,
            "class_str": class_str,
            **kwargs,
        }
