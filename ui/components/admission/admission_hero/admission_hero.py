from django_components import component


@component.register("admission_hero")
class AdmissionHero(component.Component):
    template_name = "components/admission/admission_hero/admission_hero.html"

    def get_context_data(self, title, subtitle=None, badge=None):
        return {
            "title": title,
            "subtitle": subtitle,
            "badge": badge,
        }
