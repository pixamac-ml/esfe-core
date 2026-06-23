from django_components import component


@component.register("drawer")
class Drawer(component.Component):
    template_name = "dashboard/drawer.html"

    def get_context_data(
        self,
        id="supervisor-drawer",
        content_id="supervisor-drawer-content",
        kicker="Détail",
        title="",
        placeholder="Sélectionnez un élément pour afficher les détails.",
        open_event="supervisor-drawer-open",
        close_event="supervisor-drawer-close",
        **kwargs,
    ):
        return {
            "id": id,
            "content_id": content_id,
            "kicker": kicker,
            "title": title,
            "placeholder": placeholder,
            "open_event": open_event,
            "close_event": close_event,
            **kwargs,
        }
