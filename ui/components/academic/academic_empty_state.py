from django_components import component


@component.register("academic_empty_state")
class AcademicEmptyState(component.Component):
    """État vide scolaire : liste vide, pas de résultat, action optionnelle."""

    template_name = "academic/academic_empty_state.html"

    def get_context_data(
        self,
        title="",
        message="",
        icon="info",
        compact=False,
        tone="muted",
        **kwargs,
    ):
        return {
            "title": title,
            "message": message,
            "icon": icon,
            "compact": compact,
            "tone": tone,
            **kwargs,
        }
