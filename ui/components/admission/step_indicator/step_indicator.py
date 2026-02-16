from django_components import component


@component.register("step_indicator")
class StepIndicator(component.Component):
    template_name = "components/admission/step_indicator/step_indicator.html"

    def get_context_data(self, steps, current_step):
        return {
            "steps": steps,
            "current_step": current_step,
        }
