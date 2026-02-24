from django_components import component


@component.register("comment_card")
class CommentCard(component.Component):
    template_name = "cards/comment_card/comment_card.html"

    def get_context_data(self, comment):
        return {
            "comment": comment,
            # On récupère les annotations si elles existent,
            # sinon fallback propre à 0
            "likes_count": getattr(comment, "likes_count", 0),
            "dislikes_count": getattr(comment, "dislikes_count", 0),
        }