import json

from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from admissions.models import Candidature

from accounts.dashboards.htmx_utils import manager_required


@manager_required
@require_GET
def candidature_detail(request: HttpRequest, pk: int) -> HttpResponse:
    candidature = get_object_or_404(
        Candidature.objects.select_related("programme", "branch"),
        pk=pk,
        branch=request.branch,
    )
    documents = candidature.documents.select_related("document_type").all()
    return render(
        request,
        "accounts/dashboard/partials/candidature_modal.html",
        {
            "candidature": candidature,
            "documents": documents,
        },
    )


@manager_required
@require_POST
def candidature_under_review(request: HttpRequest, pk: int) -> HttpResponse:
    candidature = get_object_or_404(Candidature, pk=pk, branch=request.branch)

    if candidature.status != "submitted":
        return HttpResponse("Seules les candidatures soumises peuvent passer en analyse.", status=400)

    candidature.status = "under_review"
    candidature.reviewed_at = timezone.now()
    candidature.reviewed_by = request.user
    candidature.save(update_fields=["status", "reviewed_at", "reviewed_by"])

    response = render(
        request,
        "accounts/dashboard/partials/manager_candidature_row.html",
        {"candidature": candidature},
    )
    response["HX-Trigger"] = json.dumps(
        {
            "candidatureUpdated": True,
            "showToast": {
                "message": "Candidature passee en analyse.",
                "type": "info",
            },
        }
    )
    return response


@manager_required
@require_POST
def candidature_accept(request: HttpRequest, pk: int) -> HttpResponse:
    candidature = get_object_or_404(Candidature, pk=pk, branch=request.branch)

    if candidature.status not in ("submitted", "under_review"):
        return HttpResponse("Cette candidature ne peut plus etre acceptee.", status=400)

    candidature.status = "accepted"
    candidature.reviewed_at = timezone.now()
    candidature.reviewed_by = request.user
    candidature.save(update_fields=["status", "reviewed_at", "reviewed_by"])
    response = render(
        request,
        "accounts/dashboard/partials/manager_candidature_row.html",
        {"candidature": candidature},
    )
    response["HX-Trigger"] = json.dumps(
        {
            "candidatureUpdated": True,
            "openInscriptionPositioning": {"url": reverse("accounts:htmx_inscription_positioning", args=[candidature.id])},
            "showToast": {"message": "Candidature acceptee. Positionnement academique requis.", "type": "success"},
        }
    )
    return response


@manager_required
@require_POST
def candidature_reject(request: HttpRequest, pk: int) -> HttpResponse:
    candidature = get_object_or_404(Candidature, pk=pk, branch=request.branch)

    if candidature.status not in ("submitted", "under_review"):
        return HttpResponse("Cette candidature ne peut plus etre refusee.", status=400)

    candidature.status = "rejected"
    candidature.rejection_reason = (request.POST.get("reason") or "").strip() or "Rejete par le gestionnaire."
    candidature.reviewed_at = timezone.now()
    candidature.reviewed_by = request.user
    candidature.save(update_fields=["status", "rejection_reason", "reviewed_at", "reviewed_by"])
    response = render(
        request,
        "accounts/dashboard/partials/manager_candidature_row.html",
        {"candidature": candidature},
    )
    response["HX-Trigger"] = json.dumps(
        {
            "candidatureUpdated": True,
            "showToast": {"message": "Candidature refusee.", "type": "warning"},
        }
    )
    return response


@manager_required
@require_POST
def candidature_to_complete(request: HttpRequest, pk: int) -> HttpResponse:
    candidature = get_object_or_404(Candidature, pk=pk, branch=request.branch)

    if candidature.status not in ("submitted", "under_review"):
        return HttpResponse("Cette candidature ne peut plus etre marquee a completer.", status=400)

    candidature.status = "to_complete"
    candidature.completion_message = (request.POST.get("message") or "").strip() or "Complements demandes par le gestionnaire."
    candidature.reviewed_at = timezone.now()
    candidature.reviewed_by = request.user
    candidature.save(update_fields=["status", "completion_message", "reviewed_at", "reviewed_by"])
    response = render(
        request,
        "accounts/dashboard/partials/manager_candidature_row.html",
        {"candidature": candidature},
    )
    response["HX-Trigger"] = json.dumps(
        {
            "candidatureUpdated": True,
            "showToast": {"message": "Complement demande au candidat.", "type": "info"},
        }
    )
    return response


@manager_required
@require_POST
def candidature_delete(request: HttpRequest, pk: int) -> HttpResponse:
    candidature = get_object_or_404(
        Candidature.objects.select_related("branch").prefetch_related("documents"),
        pk=pk,
        branch=request.branch,
        is_deleted=False,
    )

    if candidature.status != "rejected":
        return HttpResponse("Seules les candidatures rejetees peuvent etre supprimees.", status=400)

    if hasattr(candidature, "inscription"):
        return HttpResponse("Impossible de supprimer: une inscription est liee a cette candidature.", status=400)

    with transaction.atomic():
        candidature.documents.all().delete()
        candidature.is_deleted = True
        candidature.deleted_at = timezone.now()
        candidature.deleted_by = request.user
        candidature.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

    response = HttpResponse("")
    response["HX-Trigger"] = json.dumps(
        {
            "candidatureUpdated": True,
            "candidatureDeleted": {"id": pk},
            "showToast": {
                "message": "Candidature supprimee.",
                "type": "warning",
            },
        }
    )
    return response
