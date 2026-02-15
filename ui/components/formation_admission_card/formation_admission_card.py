from django_components import component

@component.register("formation_admission")
class FormationAdmission(component.Component):
    template_name = "formation_admission_card/formation_admission_card.html"

    def get_context_data(self, programme, can_apply):
        return {
            "programme": programme,
            "can_apply": can_apply,
        }
