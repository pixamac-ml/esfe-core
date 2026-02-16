from django_components import component


@component.register("reaction_bar")
class ReactionBar(component.Component):
    template_name = "ui/components/blog/reaction_bar.html"

    def get_context_data(self, article):
        return {
            "article": article
        }
