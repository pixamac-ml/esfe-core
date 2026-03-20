from django_components import component


@component.register("comment_card")
class CommentCard(component.Component):
    template_name = "cards/comment_card/comment_card.html"

    def get_context_data(self, comment, likes_count=None, dislikes_count=None):
        return {
            "comment": comment,
            # Utilise les valeurs passées si présentes, sinon fallback sur les annotations
            "likes_count": likes_count if likes_count is not None else getattr(comment, "likes_count", 0),
            "dislikes_count": dislikes_count if dislikes_count is not None else getattr(comment, "dislikes_count", 0),
        }