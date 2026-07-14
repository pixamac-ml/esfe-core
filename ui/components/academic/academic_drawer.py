from django_components import component


@component.register("academic_drawer")
class AcademicDrawer(component.Component):
    """Panneau latéral scolaire, contenu chargeable en HTMX."""

    template_name = "academic/academic_drawer.html"

    def get_context_data(
        self,
        id="academic-drawer",
        content_id="academic-drawer-content",
        kicker="Détail",
        title="",
        placeholder="Sélectionnez un élément pour afficher les détails.",
        icon="folder",
        open_event="academic-drawer-open",
        close_event="academic-drawer-close",
        position="right",
        **kwargs,
    ):
        return {
            "id": id,
            "content_id": content_id,
            "kicker": kicker,
            "title": title,
            "placeholder": placeholder,
            "icon": icon,
            "open_event": open_event,
            "close_event": close_event,
            "position": position,
            **kwargs,
        }
