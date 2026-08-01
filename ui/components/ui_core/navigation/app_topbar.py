from django_components import component


@component.register("ui_core.app_topbar")
class AppTopbar(component.Component):
    template_name = "ui_core/navigation/app_topbar.html"

    def get_context_data(
        self,
        title="",
        user_name="",
        context_label="",
        notification_count=0,
        notifications_url="",
        show_notifications_button=True,
        **kwargs,
    ):
        return {
            "title": title,
            "user_name": user_name,
            "context_label": context_label,
            "notification_count": max(int(notification_count or 0), 0),
            "notifications_url": notifications_url,
            "show_notifications_button": bool(show_notifications_button),
            **kwargs,
        }
