from django_components import component


@component.register("pagination")
class Pagination(component.Component):
    template_name = "dashboard/pagination.html"

    def get_context_data(
        self,
        total=0,
        page=1,
        per_page=20,
        hx_target="#data-table",
        hx_push_url="true",
        id="pagination",
        **kwargs,
    ):
        total_pages = max(1, -(-total // per_page))
        page = max(1, min(page, total_pages))

        window_start = max(1, page - 2)
        window_end = min(total_pages, page + 2)
        if window_end - window_start < 4:
            if window_start == 1:
                window_end = min(total_pages, window_start + 4)
            elif window_end == total_pages:
                window_start = max(1, window_end - 4)

        pages = list(range(window_start, window_end + 1))

        return {
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "pages": pages,
            "id": id,
            "hx_target": hx_target,
            "hx_push_url": hx_push_url,
            "start": (page - 1) * per_page + 1 if total > 0 else 0,
            "end": min(page * per_page, total),
            **kwargs,
        }
