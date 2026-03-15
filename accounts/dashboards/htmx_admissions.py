# accounts/dashboards/htmx_admissions.py

"""
Vues HTMX pour le dashboard admissions.

Gestion dynamique des candidatures et documents
sans rechargement de page.
"""

import json

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.template.loader import render_to_string
from django.utils import timezone
from django.db import transaction
from django.db.models import Q, Count

from admissions.models import Candidature, CandidatureDocument
from inscriptions.models import Inscription

from .permissions import check_admissions_access
from .querysets import get_base_queryset
from .helpers import get_user_branch


# ==========================================================
# DÉCORATEUR HTMX ADMISSIONS
# ==========================================================

def htmx_admissions_required(view_func):
    """
    Décorateur combiné : login + accès admissions + requête HTMX.
    """

    def wrapper(request, *args, **kwargs):

        if not request.user.is_authenticated:
            return HttpResponse(
                "<div class='text-red-500'>Non authentifié</div>",
                status=401
            )

        if not check_admissions_access(request.user):
            return HttpResponse(
                "<div class='text-red-500'>Accès refusé</div>",
                status=403
            )

        if not request.headers.get("HX-Request"):
            return HttpResponse(
                "<div class='text-red-500'>Requête HTMX requise</div>",
                status=400
            )

        return view_func(request, *args, **kwargs)

    return wrapper


# ==========================================================
# APPROBATION CANDIDATURE
# ==========================================================

@require_POST
@htmx_admissions_required
def approve_candidature_htmx(request, candidature_id):
    """
    Approuve une candidature (status -> accepted).
    """

    candidature = get_object_or_404(
        get_base_queryset(request.user, "candidature"),
        id=candidature_id
    )

    if candidature.status not in ["submitted", "under_review"]:
        return HttpResponse(
            "<div class='text-red-500'>Statut invalide pour approbation</div>",
            status=400
        )

    try:
        with transaction.atomic():

            candidature.status = "accepted"
            candidature.reviewed_at = timezone.now()
            candidature.reviewed_by = request.user
            candidature.save(update_fields=["status", "reviewed_at", "reviewed_by"])

        html = render_to_string(
            "accounts/dashboard/partials/candidature_row.html",
            {"candidature": candidature},
            request=request
        )

        response = HttpResponse(html)
        response["HX-Trigger"] = json.dumps({
            "candidatureApproved": {
                "id": candidature.id
            },
            "showToast": {
                "message": f"Candidature {candidature.reference} approuvée",
                "type": "success"
            }
        })

        return response

    except Exception as e:
        return HttpResponse(
            f"<div class='text-red-500'>Erreur : {str(e)}</div>",
            status=500
        )


# ==========================================================
# REJET CANDIDATURE
# ==========================================================

@require_POST
@htmx_admissions_required
def reject_candidature_htmx(request, candidature_id):
    """
    Rejette une candidature (status -> rejected).
    """

    candidature = get_object_or_404(
        get_base_queryset(request.user, "candidature"),
        id=candidature_id
    )

    reason = request.POST.get("reason", "").strip()

    try:
        with transaction.atomic():

            candidature.status = "rejected"
            candidature.reviewed_at = timezone.now()
            candidature.reviewed_by = request.user
            candidature.rejection_reason = reason or "Candidature non retenue"
            candidature.save(update_fields=[
                "status",
                "reviewed_at",
                "reviewed_by",
                "rejection_reason"
            ])

        html = render_to_string(
            "accounts/dashboard/partials/candidature_row.html",
            {"candidature": candidature},
            request=request
        )

        response = HttpResponse(html)
        response["HX-Trigger"] = json.dumps({
            "candidatureRejected": {
                "id": candidature.id
            },
            "showToast": {
                "message": f"Candidature {candidature.reference} rejetée",
                "type": "warning"
            }
        })

        return response

    except Exception as e:
        return HttpResponse(
            f"<div class='text-red-500'>Erreur : {str(e)}</div>",
            status=500
        )


# ==========================================================
# MISE EN RÉVISION
# ==========================================================

@require_POST
@htmx_admissions_required
def set_candidature_under_review_htmx(request, candidature_id):
    """
    Met une candidature en révision (status -> under_review).
    """

    candidature = get_object_or_404(
        get_base_queryset(request.user, "candidature"),
        id=candidature_id
    )

    if candidature.status != "submitted":
        return HttpResponse(
            "<div class='text-red-500'>Seules les candidatures soumises peuvent être mises en révision</div>",
            status=400
        )

    try:
        with transaction.atomic():

            candidature.status = "under_review"
            candidature.save(update_fields=["status"])

        html = render_to_string(
            "accounts/dashboard/partials/candidature_row.html",
            {"candidature": candidature},
            request=request
        )

        response = HttpResponse(html)
        response["HX-Trigger"] = json.dumps({
            "candidatureUpdated": {
                "id": candidature.id,
                "status": "under_review"
            },
            "showToast": {
                "message": f"Candidature {candidature.reference} en révision",
                "type": "info"
            }
        })

        return response

    except Exception as e:
        return HttpResponse(
            f"<div class='text-red-500'>Erreur : {str(e)}</div>",
            status=500
        )


# ==========================================================
# DEMANDE DE COMPLÉTION
# ==========================================================

@require_POST
@htmx_admissions_required
def set_candidature_to_complete_htmx(request, candidature_id):
    """
    Demande au candidat de compléter son dossier (status -> to_complete).
    """

    candidature = get_object_or_404(
        get_base_queryset(request.user, "candidature"),
        id=candidature_id
    )

    message = request.POST.get("message", "").strip()

    try:
        with transaction.atomic():

            candidature.status = "to_complete"
            candidature.completion_message = message or "Veuillez compléter votre dossier"
            candidature.save(update_fields=["status", "completion_message"])

        html = render_to_string(
            "accounts/dashboard/partials/candidature_row.html",
            {"candidature": candidature},
            request=request
        )

        response = HttpResponse(html)
        response["HX-Trigger"] = json.dumps({
            "candidatureUpdated": {
                "id": candidature.id,
                "status": "to_complete"
            },
            "showToast": {
                "message": f"Demande de complétion envoyée",
                "type": "info"
            }
        })

        return response

    except Exception as e:
        return HttpResponse(
            f"<div class='text-red-500'>Erreur : {str(e)}</div>",
            status=500
        )


# ==========================================================
# VALIDATION DOCUMENT
# ==========================================================

@require_POST
@htmx_admissions_required
def validate_document_htmx(request, document_id):
    """
    Valide un document de candidature.
    """

    document = get_object_or_404(
        CandidatureDocument.objects.select_related("candidature"),
        id=document_id
    )

    # Vérifier l'accès à la candidature parente
    candidature = document.candidature

    user_branch = get_user_branch(request.user)
    if user_branch and candidature.branch != user_branch:
        return HttpResponse(
            "<div class='text-red-500'>Accès refusé</div>",
            status=403
        )

    try:
        with transaction.atomic():

            document.is_validated = True
            document.validated_at = timezone.now()
            document.validated_by = request.user
            document.save(update_fields=["is_validated", "validated_at", "validated_by"])

        html = render_to_string(
            "accounts/dashboard/partials/document_row.html",
            {"document": document},
            request=request
        )

        response = HttpResponse(html)
        response["HX-Trigger"] = json.dumps({
            "documentValidated": {
                "id": document.id,
                "candidature_id": candidature.id
            },
            "showToast": {
                "message": f"Document validé",
                "type": "success"
            }
        })

        return response

    except Exception as e:
        return HttpResponse(
            f"<div class='text-red-500'>Erreur : {str(e)}</div>",
            status=500
        )


# ==========================================================
# CRÉATION INSCRIPTION
# ==========================================================

@require_POST
@htmx_admissions_required
def create_inscription_htmx(request, candidature_id):
    """
    Crée une inscription à partir d'une candidature acceptée.
    """

    candidature = get_object_or_404(
        get_base_queryset(request.user, "candidature"),
        id=candidature_id,
        status="accepted"
    )

    # Vérifier si inscription existe déjà
    if Inscription.objects.filter(candidature=candidature).exists():
        return HttpResponse(
            "<div class='text-yellow-500'>Une inscription existe déjà pour cette candidature</div>",
            status=400
        )

    try:
        with transaction.atomic():

            inscription = Inscription.objects.create(
                candidature=candidature,
                status="created"
            )

        html = render_to_string(
            "accounts/dashboard/partials/inscription_created.html",
            {
                "inscription": inscription,
                "candidature": candidature
            },
            request=request
        )

        response = HttpResponse(html)
        response["HX-Trigger"] = json.dumps({
            "inscriptionCreated": {
                "id": inscription.id,
                "candidature_id": candidature.id
            },
            "showToast": {
                "message": f"Inscription créée avec succès",
                "type": "success"
            }
        })

        return response

    except Exception as e:
        return HttpResponse(
            f"<div class='text-red-500'>Erreur : {str(e)}</div>",
            status=500
        )


# ==========================================================
# DÉTAIL CANDIDATURE
# ==========================================================

@require_GET
@htmx_admissions_required
def get_candidature_detail_htmx(request, candidature_id):
    """
    Affiche le détail complet d'une candidature dans un modal.
    """

    candidature = get_object_or_404(
        get_base_queryset(request.user, "candidature")
        .select_related(
            "programme",
            "branch",
            "reviewed_by"
        )
        .prefetch_related("documents"),
        id=candidature_id
    )

    html = render_to_string(
        "accounts/dashboard/partials/candidature_detail_modal.html",
        {"candidature": candidature},
        request=request
    )

    return HttpResponse(html)


# ==========================================================
# DÉTAIL INSCRIPTION
# ==========================================================

@require_GET
@htmx_admissions_required
def get_inscription_detail_htmx(request, inscription_id):
    """
    Affiche le détail complet d'une inscription dans un modal.
    """

    inscription = get_object_or_404(
        get_base_queryset(request.user, "inscription")
        .select_related(
            "candidature",
            "candidature__programme",
            "candidature__branch"
        )
        .prefetch_related("payments"),
        id=inscription_id
    )

    html = render_to_string(
        "accounts/dashboard/partials/inscription_detail_modal.html",
        {"inscription": inscription},
        request=request
    )

    return HttpResponse(html)


# ==========================================================
# SUPPRESSION CANDIDATURE
# ==========================================================

@require_POST
@htmx_admissions_required
def delete_candidature_htmx(request, candidature_id):
    """
    Supprime (soft delete) une candidature.
    """

    candidature = get_object_or_404(
        get_base_queryset(request.user, "candidature"),
        id=candidature_id
    )

    # Vérifier si pas d'inscription liée
    if Inscription.objects.filter(candidature=candidature).exists():
        return HttpResponse(
            "<div class='text-red-500'>Impossible de supprimer : inscription existante</div>",
            status=400
        )

    try:
        with transaction.atomic():

            candidature.is_deleted = True
            candidature.deleted_at = timezone.now()
            candidature.deleted_by = request.user
            candidature.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

        response = HttpResponse("")
        response["HX-Trigger"] = json.dumps({
            "candidatureDeleted": {
                "id": candidature.id
            },
            "showToast": {
                "message": f"Candidature supprimée",
                "type": "warning"
            }
        })

        return response

    except Exception as e:
        return HttpResponse(
            f"<div class='text-red-500'>Erreur : {str(e)}</div>",
            status=500
        )


# ==========================================================
# LISTE CANDIDATURES PAGINÉE
# ==========================================================

@require_GET
@htmx_admissions_required
def candidatures_list_htmx(request):
    """
    Liste paginée des candidatures avec filtres.

    Utilisé pour le chargement dynamique et la recherche.
    """

    candidatures = (
        get_base_queryset(request.user, "candidature")
        .select_related(
            "programme",
            "branch"
        )
        .filter(is_deleted=False)
    )

    # Filtres
    status = request.GET.get("status")
    programme_id = request.GET.get("programme")
    search = request.GET.get("q")

    if status:
        candidatures = candidatures.filter(status=status)

    if programme_id:
        candidatures = candidatures.filter(programme_id=programme_id)

    if search:
        candidatures = candidatures.filter(
            Q(reference__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search)
        )

    # Tri
    order = request.GET.get("order", "recent")

    if order == "oldest":
        candidatures = candidatures.order_by("created_at")
    elif order == "name":
        candidatures = candidatures.order_by("last_name", "first_name")
    else:
        candidatures = candidatures.order_by("-created_at")

    # Pagination
    from django.core.paginator import Paginator

    paginator = Paginator(candidatures, 25)
    page = request.GET.get("page", 1)
    candidatures_page = paginator.get_page(page)

    html = render_to_string(
        "accounts/dashboard/partials/candidatures_table.html",
        {
            "candidatures": candidatures_page,
            "paginator": paginator
        },
        request=request
    )

    return HttpResponse(html)


# ==========================================================
# LISTE DOCUMENTS
# ==========================================================

@require_GET
@htmx_admissions_required
def documents_list_htmx(request):
    """
    Liste des documents en attente de validation.
    """

    # Documents non validés des candidatures accessibles
    candidature_ids = (
        get_base_queryset(request.user, "candidature")
        .filter(is_deleted=False)
        .values_list("id", flat=True)
    )

    documents = (
        CandidatureDocument.objects
        .filter(
            candidature_id__in=candidature_ids,
            is_validated=False
        )
        .select_related(
            "candidature",
            "candidature__programme"
        )
        .order_by("-uploaded_at")
    )

    # Filtre par type de document
    doc_type = request.GET.get("type")
    if doc_type:
        documents = documents.filter(document_type=doc_type)

    # Pagination
    from django.core.paginator import Paginator

    paginator = Paginator(documents, 20)
    page = request.GET.get("page", 1)
    documents_page = paginator.get_page(page)

    html = render_to_string(
        "accounts/dashboard/partials/documents_table.html",
        {
            "documents": documents_page,
            "paginator": paginator
        },
        request=request
    )

    return HttpResponse(html)


# ==========================================================
# RAFRAÎCHIR STATS ADMISSIONS
# ==========================================================

@require_GET
@htmx_admissions_required
def refresh_admissions_stats_htmx(request):
    """
    Rafraîchit les statistiques du dashboard admissions.

    Utilisé pour la mise à jour automatique des compteurs.
    """

    candidatures = (
        get_base_queryset(request.user, "candidature")
        .filter(is_deleted=False)
    )

    # Comptage par statut
    stats = candidatures.aggregate(
        total=Count("id"),
        submitted=Count("id", filter=Q(status="submitted")),
        under_review=Count("id", filter=Q(status="under_review")),
        to_complete=Count("id", filter=Q(status="to_complete")),
        accepted=Count("id", filter=Q(status="accepted")),
        rejected=Count("id", filter=Q(status="rejected")),
    )

    # Documents en attente
    candidature_ids = candidatures.values_list("id", flat=True)
    pending_documents = (
        CandidatureDocument.objects
        .filter(
            candidature_id__in=candidature_ids,
            is_validated=False
        )
        .count()
    )

    stats["pending_documents"] = pending_documents

    # Stats du jour
    today = timezone.now().date()
    stats["today"] = candidatures.filter(created_at__date=today).count()

    html = render_to_string(
        "accounts/dashboard/partials/admissions_stats.html",
        {"stats": stats},
        request=request
    )

    return HttpResponse(html)