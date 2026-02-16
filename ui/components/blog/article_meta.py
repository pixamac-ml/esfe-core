from django_components import component


@component.register("article_meta")
class ArticleMeta(component.Component):
    template_name = "ui/components/blog/article_meta.html"

    def get_context_data(self, article):
        return {
            "article": article
        }
