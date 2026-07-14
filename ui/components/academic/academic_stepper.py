from django_components import component


@component.register("academic_stepper")
class AcademicStepper(component.Component):
    """Stepper scolaire horizontal ou vertical (admission, inscription, notes)."""

    template_name = "academic/academic_stepper.html"

    def get_context_data(
        self,
        steps=None,
        current_step=1,
        layout="horizontal",
        class_str="",
        **kwargs,
    ):
        return {
            "steps": steps or [],
            "current_step": current_step,
            "layout": layout,
            "class_str": class_str,
            **kwargs,
        }
