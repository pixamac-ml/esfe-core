from __future__ import annotations

from urllib.parse import urlencode

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q

from portal.models import AdministrativeDocument


def _page(queryset, page_number, *, per_page=10):
    paginator = Paginator(queryset, per_page)
    try:
        return paginator.page(page_number or 1)
    except (EmptyPage, PageNotAnInteger):
        return paginator.page(1)


def build_director_administrative_document_context(
    *,
    branch,
    subview="overview",
    query="",
    status="",
    document_type="",
    page_number=1,
    selected_document_id=None,
):
    documents = AdministrativeDocument.objects.none()
    if branch is not None:
        documents = AdministrativeDocument.objects.select_related("created_by").filter(
            branch=branch
        )

    metrics = {
        "total": documents.count(),
        "draft": documents.filter(status=AdministrativeDocument.STATUS_DRAFT).count(),
        "published": documents.filter(status=AdministrativeDocument.STATUS_PUBLISHED).count(),
    }
    query = (query or "").strip()
    status = status if status in dict(AdministrativeDocument.STATUS_CHOICES) else ""
    document_type = (
        document_type
        if document_type in dict(AdministrativeDocument.TYPE_CHOICES)
        else ""
    )
    filtered = documents
    if query:
        filtered = filtered.filter(
            Q(title__icontains=query)
            | Q(reference__icontains=query)
            | Q(recipients__icontains=query)
            | Q(body__icontains=query)
        )
    if status:
        filtered = filtered.filter(status=status)
    if document_type:
        filtered = filtered.filter(doc_type=document_type)

    selected_document = None
    if str(selected_document_id or "").isdigit():
        selected_document = documents.filter(pk=int(selected_document_id)).first()

    params = {"view": subview}
    if query:
        params["document_q"] = query
    if status:
        params["document_status"] = status
    if document_type:
        params["document_type"] = document_type

    page = _page(filtered.order_by("-created_at", "-id"), page_number)
    return {
        "administrative_documents_page": page,
        "administrative_document_metrics": metrics,
        "administrative_document_selected": selected_document,
        "administrative_document_filtered_count": page.paginator.count,
        "administrative_document_q": query,
        "administrative_document_status": status,
        "administrative_document_type": document_type,
        "administrative_document_query_suffix": urlencode(params),
        "administrative_document_type_choices": AdministrativeDocument.TYPE_CHOICES,
        "administrative_document_status_choices": AdministrativeDocument.STATUS_CHOICES,
    }
