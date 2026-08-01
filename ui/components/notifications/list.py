from django_components import component


@component.register("notifications.list")
class NotificationList(component.Component):
    template_name = "notifications/list.html"

    def get_context_data(
        self,
        notifications=None,
        empty_message="Aucune notification",
        empty_icon="bell-off",
        loading=False,
        hx_load_more="",
        filter_url="",
        mark_all_read_url="",
        detail_target="",
        detail_opens_drawer=False,
        **kwargs,
    ):
        return {
            "notifications": notifications or [],
            "empty_message": empty_message,
            "empty_icon": empty_icon,
            "loading": bool(loading),
            "hx_load_more": hx_load_more,
            "filter_url": filter_url,
            "mark_all_read_url": mark_all_read_url,
            "detail_target": detail_target,
            "detail_opens_drawer": bool(detail_opens_drawer),
        }
