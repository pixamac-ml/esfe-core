from django_components import component


@component.register("programme_grid")
class ProgrammeGrid(component.Component):
    template_name = "programme_grid/programme_grid.html"

    def get_context_data(self, programmes, page_obj, total_programmes, current_cycle=None, search_query=None):
        return {
            "programmes": programmes,
            "page_obj": page_obj,
            "total_programmes": total_programmes,
            "current_cycle": current_cycle,
            "search_query": search_query,
        }