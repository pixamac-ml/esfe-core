from django_components import component


@component.register("notifications.item")
class NotificationItem(component.Component):
    template_name = "notifications/item.html"

    def get_context_data(
        self,
        notification_id="",
        title="",
        summary="",
        icon="bell",
        source="",
        time_ago="",
        is_read=False,
        priority="normal",
        action_url="#",
        hx_mark_read="",
        detail_url="",
        detail_target="",
        detail_opens_drawer=False,
        **kwargs,
    ):
        return {
            "notification_id": notification_id,
            "title": title,
            "summary": summary,
            "icon": icon,
            "source": source,
            "time_ago": time_ago,
            "is_read": bool(is_read),
            "priority": priority,
            "action_url": action_url,
            "hx_mark_read": hx_mark_read,
            "detail_url": detail_url,
            "detail_target": detail_target,
            "detail_opens_drawer": bool(detail_opens_drawer),
        }
