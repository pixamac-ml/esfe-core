from django_components import component


@component.register("blog_article_detail")
class BlogArticleDetail(component.Component):
    template_name = "ui/sections/blog_article_detail/blog_article_detail.html"

    def get_context_data(self, article, comments, related_articles):
        return {
            "article": article,
            "comments": comments,
            "related_articles": related_articles,
        }
