from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.views.decorators.http import require_POST, require_GET
from django.utils import timezone
from django.db.models import Q

from admissions.models import Candidature, CandidatureDocument
from inscriptions.models import Inscription
from payments.models import Payment

from accounts.dashboards.helpers import get_user_branch, is_manager


def manager_required(view_func):
    """Décorateur gestionnaire."""

    def wrapper(request, *args, **kwargs):
        if not is_manager(request.user):
            return HttpResponse("Non autorisé", status=403)
        branch = get_user_branch(request.user)
        if not branch:
            return HttpResponse("Annexe non trouvée", status=403)
        request.branch = branch
        return view_func(request, *args, **kwargs)

    return login_required(wrapper)


# =============================================
# CANDIDATURES
# =============================================

@manager_required
@require_GET
def candidature_detail(request, pk):
    """Modal détail candidature."""
    candidature = get_object_or_404(
        Candidature.objects.select_related("programme", "branch"),
        pk=pk,
        branch=request.branch
    )
    documents = candidature.documents.select_related("document_type").all()

    context = {
        "candidature": candidature,
        "documents": documents,
    }
    return render(request, "accounts/dashboard/partials/candidature_modal.html", context)


@manager_required
@require_POST
def candidature_accept(request, pk):
    """Accepter une candidature."""
    candidature = get_object_or_404(Candidature, pk=pk, branch=request.branch)

    candidature.status = "accepted"
    candidature.reviewed_at = timezone.now()
    candidature.reviewed_by = request.user
    candidature.save(update_fields=["status", "reviewed_at", "reviewed_by"])

    return render(request, "accounts/dashboard/partials/candidature_row.html", {
        "candidature": candidature,
        "message": "Candidature acceptée avec succès"
    })


@manager_required
@require_POST
def candidature_reject(request, pk):
    """Rejeter une candidature."""
    candidature = get_object_or_404(Candidature, pk=pk, branch=request.branch)
    reason = request.POST.get("reason", "")

    candidature.status = "rejected"
    candidature.rejection_reason = reason
    candidature.reviewed_at = timezone.now()
    candidature.reviewed_by = request.user
    candidature.save(update_fields=["status", "rejection_reason", "reviewed_at", "reviewed_by"])

    return render(request, "accounts/dashboard/partials/candidature_row.html", {
        "candidature": candidature,
        "message": "Candidature refusée"
    })


@manager_required
@require_POST
def candidature_to_complete(request, pk):
    """Marquer à compléter."""
    candidature = get_object_or_404(Candidature, pk=pk, branch=request.branch)
    message = request.POST.get("message", "")

    candidature.status = "to_complete"
    candidature.completion_message = message
    candidature.save(update_fields=["status", "completion_message"])

    return render(request, "accounts/dashboard/partials/candidature_row.html", {
        "candidature": candidature,
        "message": "Demande de complétion envoyée"
    })


# =============================================
# INSCRIPTIONS
# =============================================

@manager_required
@require_GET
def inscription_detail(request, pk):
    """Modal détail inscription."""
    inscription = get_object_or_404(
        Inscription.objects.select_related(
            "candidature",
            "candidature__programme",
        ),
        pk=pk,
        candidature__branch=request.branch
    )
    payments = inscription.payments.all().order_by("-created_at")

    context = {
        "inscription": inscription,
        "payments": payments,
    }
    return render(request, "accounts/dashboard/partials/inscription_modal.html", context)


@manager_required
@require_POST
def inscription_create(request, pk):
    """Créer une inscription depuis une candidature acceptée."""
    candidature = get_object_or_404(
        Candidature,
        pk=pk,
        branch=request.branch,
        status__in=["accepted", "accepted_with_reserve"]
    )

    # Vérifier si inscription existe déjà
    if hasattr(candidature, "inscription"):
        return HttpResponse(
            '<div class="text-red-600">Une inscription existe déjà pour cette candidature.</div>',
            status=400
        )

    # Calculer le montant
    amount = candidature.programme.get_inscription_amount_for_year(candidature.entry_year)
    if amount == 0:
        amount = 500000  # Montant par défaut

    inscription = Inscription.objects.create(
        candidature=candidature,
        amount_due=amount,
        status=Inscription.STATUS_AWAITING_PAYMENT
    )

    return HttpResponse(f'''
        <div class="bg-green-100 text-green-800 px-4 py-3 rounded-lg">
            Inscription créée avec succès ! Référence : {inscription.public_token}
        </div>
    ''')


# =============================================
# PAIEMENTS
# =============================================

@manager_required
@require_GET
def payment_detail(request, pk):
    """Modal détail paiement."""
    payment = get_object_or_404(
        Payment.objects.select_related(
            "inscription__candidature",
            "inscription__candidature__programme",
            "agent__user",
        ),
        pk=pk,
        inscription__candidature__branch=request.branch
    )

    context = {"payment": payment}
    return render(request, "accounts/dashboard/partials/payment_modal.html", context)


@manager_required
@require_POST
def payment_validate(request, pk):
    """Valider un paiement."""
    payment = get_object_or_404(
        Payment,
        pk=pk,
        inscription__candidature__branch=request.branch,
        status=Payment.STATUS_PENDING
    )

    payment.status = Payment.STATUS_VALIDATED
    payment.save()

    return render(request, "accounts/dashboard/partials/payment_row.html", {
        "payment": payment,
        "message": "Paiement validé avec succès"
    })


@manager_required
@require_POST
def payment_cancel(request, pk):
    """Annuler un paiement."""
    payment = get_object_or_404(
        Payment,
        pk=pk,
        inscription__candidature__branch=request.branch,
        status=Payment.STATUS_PENDING
    )

    payment.status = Payment.STATUS_CANCELLED
    payment.save()

    # Mettre à jour l'inscription
    payment.inscription.update_financial_state()

    return render(request, "accounts/dashboard/partials/payment_row.html", {
        "payment": payment,
        "message": "Paiement annulé"
    })


# =============================================
# RECHERCHE GLOBALE
# =============================================

@manager_required
@require_GET
def global_search(request):
    """Recherche globale."""
    q = request.GET.get("q", "").strip()
    branch = request.branch

    if len(q) < 2:
        return HttpResponse("")

    # Recherche candidatures
    candidatures = Candidature.objects.filter(
        branch=branch,
        is_deleted=False
    ).filter(
        Q(first_name__icontains=q) |
        Q(last_name__icontains=q) |
        Q(email__icontains=q)
    )[:5]

    # Recherche inscriptions
    inscriptions = Inscription.objects.filter(
        candidature__branch=branch
    ).filter(
        Q(candidature__first_name__icontains=q) |
        Q(candidature__last_name__icontains=q) |
        Q(public_token__icontains=q)
    ).select_related("candidature")[:5]

    # Recherche paiements
    payments = Payment.objects.filter(
        inscription__candidature__branch=branch
    ).filter(
        Q(reference__icontains=q) |
        Q(inscription__candidature__last_name__icontains=q)
    ).select_related("inscription__candidature")[:5]

    context = {
        "candidatures": candidatures,
        "inscriptions": inscriptions,
        "payments": payments,
        "query": q,
    }

    return render(request, "accounts/dashboard/partials/search_results.html", context)