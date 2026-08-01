from django_components import component


@component.register("notifications.badge")
class NotificationBadge(component.Component):
    template_name = "notifications/badge.html"

    def get_context_data(
        self,
        count=0,
        max_count=99,
        size="sm",
        **kwargs,
    ):
        return {
            "count": int(count),
            "max_count": int(max_count),
            "size": size if size in {"sm", "md", "lg"} else "sm",
        }
