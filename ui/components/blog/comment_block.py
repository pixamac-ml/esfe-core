from django_components import component


@component.register("comment_block")
class CommentBlock(component.Component):
    template_name = "blog/comment_block.html"

    def get_context_data(self, comment):
        return {
            "comment": comment
        }
