from django_components import component


@component.register("import_panel")
class ImportPanel(component.Component):
    template_name = "informaticien/import_panel.html"

    def get_context_data(self, classes, selected_class=None, semesters=None, selected_semester=None, feedback=None):
        return {
            "classes": classes,
            "selected_class": selected_class,
            "semesters": semesters or [],
            "selected_semester": selected_semester,
            "feedback": feedback,
        }
