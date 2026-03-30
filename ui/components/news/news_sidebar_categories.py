from django_components import component


@component.register("news_sidebar_categories")
class NewsSidebarCategories(component.Component):
    template_name = "news/news_sidebar_categories.html"

    def get_context_data(self, categories, current_category=None, current_search=""):
        return {
            "categories": categories,
            "current_category": current_category,
            "current_search": current_search,
        }
