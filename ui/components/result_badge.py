from django_components import component


@component.register("result_badge")
class ResultBadge(component.Component):
    template_name = "components/result_badge.html"

    def get_context_data(self, result):
        return {
            "result": result,
        }