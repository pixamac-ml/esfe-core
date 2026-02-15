from django_components import component


@component.register("programme_filters")
class ProgrammeFilters(component.Component):
    template_name = "programme_filters/programme_filters.html"

    def get_context_data(self, cycles, current_cycle=None, search_query=None):
        return {
            "cycles": cycles,
            "current_cycle": current_cycle,
            "search_query": search_query,
        }
