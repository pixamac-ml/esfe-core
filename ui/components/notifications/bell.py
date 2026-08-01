from django_components import component


@component.register("notifications.bell")
class NotificationBell(component.Component):
    template_name = "notifications/bell.html"

    def get_context_data(
        self,
        unread_count=0,
        preview_url="#",
        preview_target="",
        center_url="#",
        center_target="",
        **kwargs,
    ):
        return {
            "unread_count": int(unread_count),
            "preview_url": preview_url,
            "preview_target": preview_target,
            "center_url": center_url,
            "center_target": center_target,
        }
