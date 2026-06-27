from django_components import component


@component.register("search_bar")
class SearchBar(component.Component):
    template_name = "dashboard/search_bar.html"

    def get_context_data(self, name="search", placeholder="Rechercher...", hx_target="", hx_post="", value="", **kwargs):
        return {
            "name": name,
            "placeholder": placeholder,
            "hx_target": hx_target,
            "hx_post": hx_post,
            "value": value,
            **kwargs,
        }
