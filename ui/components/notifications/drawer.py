from django_components import component


@component.register("notifications.drawer")
class NotificationDrawer(component.Component):
    template_name = "notifications/drawer.html"

    def get_context_data(
        self,
        drawer_id="notification-drawer",
        title="Notifications",
        notifications=None,
        hx_load="",
        mark_all_read_url="",
        center_url="#",
        **kwargs,
    ):
        return {
            "drawer_id": drawer_id,
            "title": title,
            "notifications": notifications or [],
            "hx_load": hx_load,
            "mark_all_read_url": mark_all_read_url,
            "center_url": center_url,
        }
