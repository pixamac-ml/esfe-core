from django_components import component


@component.register("portal_notification_bell")
class PortalNotificationBell(component.Component):
    """
    Cloche de notification universelle avec dropdown aperçu.

    Params:
        unread_count    – nombre de notifications non lues (int)
        preview_items   – liste de dicts [{title, body, created_at, is_read, url}]
        notifications_url  – URL vers la section notifications du dashboard courant
        center_url      – URL vers le centre de notifications complet (optionnel)
        htmx_target     – sélecteur CSS du workspace à cibler (ex: "#secretary-workspace")
    """
    template_name = "dashboard/portal_notification_bell.html"

    def get_context_data(
        self,
        unread_count=0,
        preview_items=None,
        notifications_url="?section=notifications",
        center_url="",
        htmx_target="",
        **kwargs,
    ):
        return {
            "unread_count": unread_count,
            "preview_items": (preview_items or [])[:5],
            "notifications_url": notifications_url,
            "center_url": center_url,
            "htmx_target": htmx_target,
            **kwargs,
        }
