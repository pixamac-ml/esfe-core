from django_components import component


@component.register("category_badge")
class CategoryBadge(component.Component):
    template_name = "blog/category_badge.html"

    def get_context_data(self, category):
        return {
            "category": category
        }
