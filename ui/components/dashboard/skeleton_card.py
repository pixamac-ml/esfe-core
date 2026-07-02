from django_components import component


@component.register("skeleton_card")
class SkeletonCard(component.Component):
    template_name = "dashboard/skeleton_card.html"

    def get_context_data(self, size="lg", lines=3, **kwargs):
        sizes = {
            "sm": {"card": "px-3 py-2.5", "title": "h-3 w-16", "line1": "h-4 w-10", "line2": ""},
            "md": {"card": "px-4 py-3.5", "title": "h-3 w-20", "line1": "h-5 w-14", "line2": "h-2 w-24 mt-2"},
            "lg": {"card": "px-4 py-4", "title": "h-3 w-24", "line1": "h-7 w-16", "line2": "h-2 w-24 mt-2"},
        }
        return {
            "size": size,
            "card_class": sizes.get(size, sizes["lg"])["card"],
            "title_class": sizes.get(size, sizes["lg"])["title"],
            "line1_class": sizes.get(size, sizes["lg"])["line1"],
            "line2_class": sizes.get(size, sizes["lg"])["line2"],
            **kwargs,
        }
