from django_components import component


@component.register("academic_toolbar")
class AcademicToolbar(component.Component):
    """Barre d'outils scolaire : titre, compteur, actions."""

    template_name = "academic/academic_toolbar.html"

    def get_context_data(
        self,
        title="",
        total_count=0,
        count_label="résultat",
        class_str="",
        **kwargs,
    ):
        return {
            "title": title,
            "total_count": total_count,
            "count_label": count_label,
            "class_str": class_str,
            **kwargs,
        }
