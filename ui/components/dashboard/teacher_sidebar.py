from django_components import component


@component.register("teacher_sidebar")
class TeacherSidebar(component.Component):
    template_name = "dashboard/teacher_sidebar.html"

    def get_context_data(
        self,
        active_section="overview",
        user_display_name="",
        branch_name="",
        pending_lesson_logs_count=0,
        notifications_count=0,
        **kwargs,
    ):
        return {
            "active_section": active_section,
            "user_display_name": user_display_name,
            "branch_name": branch_name,
            "pending_lesson_logs_count": pending_lesson_logs_count,
            "notifications_count": notifications_count,
            **kwargs,
        }
