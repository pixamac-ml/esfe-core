from django_components import component


@component.register("attendance_workflow")
class AttendanceWorkflow(component.Component):
    template_name = "components/attendance_workflow.html"

    def get_context_data(self, workflow=None, class_picker_items=None, **kwargs):
        return {
            "workflow": workflow,
            "class_picker_items": class_picker_items or [],
        }
