from django_components import component


@component.register("semester_summary")
class SemesterSummary(component.Component):
    template_name = "notes/semester_summary.html"

    def get_context_data(self, row):
        return {"row": row}
