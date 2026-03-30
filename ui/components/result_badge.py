from django_components import component


@component.register("result_badge")
class ResultBadge(component.Component):
    template_name = "components/result_badge.html"

    def get_context_data(self, result, rank=None, total_count=None):
        rank = int(rank or 1)
        total = int(total_count or 0)

        if total > 0:
            progress = int(((total - rank + 1) * 100) / total)
            progress = max(8, min(progress, 100))
        else:
            progress = max(12, 100 - ((rank - 1) * 6))

        return {
            "result": result,
            "rank": rank,
            "progress": progress,
        }