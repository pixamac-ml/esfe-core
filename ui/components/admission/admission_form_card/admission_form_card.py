from django_components import component


@component.register("admission_form_card")
class AdmissionFormCard(component.Component):
    template_name = "components/admission/admission_form_card/admission_form_card.html"

    def get_context_data(self, title):
        return {
            "title": title,
        }
