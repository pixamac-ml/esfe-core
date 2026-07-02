from django_components import component


@component.register("teacher_overview_section")
class TeacherOverviewSection(component.Component):
    template_name = "dashboard/teacher_overview_section.html"

    def get_context_data(self, kpi_cards=None, today_events=None, upcoming_events=None,
                         recent_lesson_logs=None, recent_supports=None,
                         teacher_insights=None, **kwargs):
        return {
            "active_section": "overview",
            "kpi_cards": kpi_cards or [],
            "today_events": today_events or [],
            "upcoming_events": upcoming_events or [],
            "recent_lesson_logs": recent_lesson_logs or [],
            "recent_supports": recent_supports or [],
            "teacher_insights": teacher_insights or [],
            **kwargs,
        }
