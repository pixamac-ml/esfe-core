from django_components import component


@component.register("import_panel")
class ImportPanel(component.Component):
    template_name = "informaticien/import_panel.html"

    def get_context_data(
        self,
        classes,
        selected_class=None,
        semesters=None,
        selected_semester=None,
        feedback=None,
        ues=None,
        student_count=0,
        ec_count=0,
        workflow_permissions=None,
        notes_state=None,
        import_preview=None,
    ):
        return {
            "classes": classes,
            "selected_class": selected_class,
            "semesters": semesters or [],
            "selected_semester": selected_semester,
            "feedback": feedback,
            "ues": ues or [],
            "student_count": student_count,
            "ec_count": ec_count,
            "workflow_permissions": workflow_permissions,
            "notes_state": notes_state,
            "import_preview": import_preview,
        }
