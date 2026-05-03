from django_components import component


@component.register("timetable_view")
class TimetableView(component.Component):
    template_name = "components/timetable_view.html"

    def get_context_data(self, timetable_view=None, **kwargs):
        return {"timetable_view": timetable_view or {}}
