from django_components import component


@component.register("portal_notifications_section")
class PortalNotificationsSection(component.Component):
    """
    Section notifications universelle — utilisable dans tous les portails.

    Params:
        panel_id           – id HTML du panneau
        notifications_rows – queryset ou liste de NotificationMessage
        notifications_page – objet Page Django (optionnel, pour pagination)
        selected_notification – objet NotificationMessage sélectionné (optionnel)
        unread_count       – nombre de non lues
        hx_target          – sélecteur pour pagination HTMX
    """
    template_name = "dashboard/portal_notifications_section.html"

    def get_context_data(
        self,
        panel_id="portal-panel-notifications",
        notifications_rows=None,
        notifications_page=None,
        selected_notification=None,
        unread_count=0,
        hx_target="",
        **kwargs,
    ):
        return {
            "panel_id": panel_id,
            "notifications_rows": notifications_rows or [],
            "notifications_page": notifications_page,
            "selected_notification": selected_notification,
            "unread_count": unread_count,
            "hx_target": hx_target,
            **kwargs,
        }
