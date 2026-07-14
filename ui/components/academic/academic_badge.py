from django_components import component


@component.register("academic_badge")
class AcademicBadge(component.Component):
    """Badge scolaire : statut, niveau, rôle, pastille."""

    template_name = "academic/academic_badge.html"

    def get_context_data(
        self,
        label="",
        tone="neutral",
        icon="",
        dot=False,
        pulse=False,
        class_str="",
        **kwargs,
    ):
        return {
            "label": label,
            "tone": tone,
            "icon": icon,
            "dot": dot,
            "pulse": pulse,
            "class_str": class_str,
            **kwargs,
        }
