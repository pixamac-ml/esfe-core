from django_components import component


@component.register("comment_form")
class CommentForm(component.Component):
    template_name = "blog/comment_form.html"

    def get_context_data(self, article):
        return {
            "article": article
        }