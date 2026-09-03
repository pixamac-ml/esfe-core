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
        active_session_type="normal",
    ):
        return {
            "classes": classes,
            "class_options": [
                {"value": "", "label": "Sélectionner une classe"},
                *[
                    {
                        "value": academic_class.id,
                        "label": f"{academic_class.display_name} — {academic_class.academic_year.name}",
                    }
                    for academic_class in classes
                ],
            ],
            "selected_class": selected_class,
            "not_selected_class": selected_class is None,
            "semesters": semesters or [],
            "semester_options": [
                {"value": "", "label": "Sélectionner un semestre"},
                *[
                    {
                        "value": semester.id,
                        "label": f"Semestre {semester.number} — {semester.get_status_display()}",
                    }
                    for semester in (semesters or [])
                ],
            ],
            "selected_semester": selected_semester,
            "feedback": feedback,
            "ues": ues or [],
            "student_count": student_count,
            "ec_count": ec_count,
            "workflow_permissions": workflow_permissions,
            "notes_state": notes_state,
            "import_preview": import_preview,
            "active_session_type": active_session_type,
            "session_label": "Rattrapage" if active_session_type == "retake" else "Normale",
        }
