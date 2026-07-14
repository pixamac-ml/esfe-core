from django_components import component


@component.register("academic_card")
class AcademicCard(component.Component):
    """Conteneur de contenu académique réutilisable pour les dashboards."""

    template_name = "academic/academic_card.html"

    def get_context_data(
        self,
        padding="md",
        elevated=False,
        extra_class="",
        title="",
        subtitle="",
        icon="",
        **kwargs,
    ):
        return {
            "padding": padding,
            "elevated": elevated,
            "extra_class": extra_class,
            "title": title,
            "subtitle": subtitle,
            "icon": icon,
            **kwargs,
        }
