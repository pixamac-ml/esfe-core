from django_components import component


@component.register("secretary_topbar")
class SecretaryTopbar(component.Component):
    template_name = "dashboard/secretary_topbar.html"

    def get_context_data(
        self,
        branch_name="",
        user_display_name="",
        notifications_count=0,
        **kwargs,
    ):
        return {
            "branch_name": branch_name,
            "user_display_name": user_display_name,
            "notifications_count": notifications_count,
            **kwargs,
        }
