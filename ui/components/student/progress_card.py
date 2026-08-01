from django_components import component


@component.register("student.progress_card")
class StudentProgressCard(component.Component):
    template_name = "student/progress_card.html"

    def get_context_data(
        self,
        title="Progression académique",
        items=None,
        overall_percentage=0,
        overall_label="",
        **kwargs,
    ):
        return {
            "title": title,
            "items": items or [],
            "overall_percentage": int(overall_percentage),
            "overall_label": overall_label,
        }
