from django_components import component


@component.register("reaction_bar")
class ReactionBar(component.Component):
    template_name = "blog/reaction_bar.html"

    def get_context_data(self, article):
        return {
            "article": article
        }
