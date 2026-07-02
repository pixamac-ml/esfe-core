from django_components import component


@component.register("teacher_topbar")
class TeacherTopbar(component.Component):
    template_name = "dashboard/teacher_topbar.html"

    def get_context_data(
        self,
        user_display_name="",
        branch_name="",
        notifications_count=0,
        **kwargs,
    ):
        return {
            "user_display_name": user_display_name,
            "branch_name": branch_name,
            "notifications_count": notifications_count,
            **kwargs,
        }
