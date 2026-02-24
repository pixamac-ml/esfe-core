from django_components import component


@component.register("result_sidebar")
class ResultSidebar(component.Component):
    template_name = "components/result_sidebar.html"

    def get_context_data(
        self,
        annees,
        annexes_par_annee,
        current_annee=None,
        current_annexe=None,
    ):
        return {
            "annees": annees,
            "annexes_par_annee": annexes_par_annee,
            "current_annee": current_annee,
            "current_annexe": current_annexe,
        }