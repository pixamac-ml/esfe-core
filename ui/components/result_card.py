from django_components import component, Component


@component.register("result_card")
class ResultCard(Component):
    template_name = "components/result_card.html"

    def get_context_data(self, result):
        return {"result": result}