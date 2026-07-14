from django_components import component


@component.register("academic_modal")
class AcademicModal(component.Component):
    """Modale scolaire générique, contrôlable par Alpine.js."""

    template_name = "academic/academic_modal.html"

    def get_context_data(
        self,
        id="academic-modal",
        title="",
        open_label="Ouvrir",
        size="md",
        show_footer=True,
        **kwargs,
    ):
        return {
            "id": id,
            "title": title,
            "open_label": open_label,
            "size": size,
            "show_footer": show_footer,
            **kwargs,
        }
