from django_components import component


@component.register("comment_card")
class CommentCard(component.Component):
    template_name = "ui/cards/comment_card/comment_card.html"

    def get_context_data(self, comment):
        return {
            "comment": comment,
            "likes_count": comment.reactions.filter(reaction_type="like").count(),
            "dislikes_count": comment.reactions.filter(reaction_type="dislike").count(),
        }
