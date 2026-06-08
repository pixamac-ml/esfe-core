from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from academics.models import AcademicClass
from academics.services.academic_positioning import get_positioning_fee_for_level
from admissions.models import Candidature
from inscriptions.models import Inscription

from accounts.dashboards.htmx_utils import (
    PAYABLE_INSCRIPTION_STATUSES,
    _render_manager_academic_positioning_modal,
    get_active_cash_session,
    get_current_agent,
    manager_required,
)


@manager_required
@require_GET
def inscription_detail(request: HttpRequest, pk: int) -> HttpResponse:
    inscription = get_object_or_404(
        Inscription.objects.select_related(
            "candidature",
            "candidature__programme",
            "candidature__branch",
        ).prefetch_related("payments"),
        pk=pk,
        candidature__branch=request.branch,
    )
    manager_agent = get_current_agent(request.user, request.branch)
    active_cash_session = get_active_cash_session(inscription)
    return render(
        request,
        "accounts/dashboard/partials/inscription_modal.html",
        {
            "inscription": inscription,
            "payments": inscription.payments.all().order_by("-created_at"),
            "manager_agent": manager_agent,
            "active_cash_session": active_cash_session,
            "can_create_cash_session": (
                manager_agent
                and inscription.status in PAYABLE_INSCRIPTION_STATUSES
                and inscription.balance > 0
                and active_cash_session is None
            ),
        },
    )


@manager_required
@require_GET
def inscription_positioning_modal(request: HttpRequest, pk: int) -> HttpResponse:
    candidature = get_object_or_404(
        Candidature,
        pk=pk,
        branch=request.branch,
        status__in=["accepted", "accepted_with_reserve"],
    )

    if hasattr(candidature, "inscription"):
        return HttpResponse("Inscription deja creee", status=400)

    return _render_manager_academic_positioning_modal(request, candidature)


@manager_required
@require_POST
def inscription_create(request: HttpRequest, pk: int) -> HttpResponse:
    candidature = get_object_or_404(
        Candidature,
        pk=pk,
        branch=request.branch,
        status__in=["accepted", "accepted_with_reserve"],
    )

    if hasattr(candidature, "inscription"):
        return HttpResponse(
            '<tr><td colspan="5" class="px-6 py-4 text-sm text-red-600">Une inscription existe deja pour cette candidature.</td></tr>',
            status=400,
        )

    selected_level = request.POST.get("academic_level", "").strip().upper()
    academic_class_id = request.POST.get("academic_class", "").strip()
    academic_class = (
        AcademicClass.objects.select_related("programme", "branch", "academic_year")
        .filter(pk=academic_class_id)
        .first()
    )

    if not academic_class:
        return _render_manager_academic_positioning_modal(
            request,
            candidature,
            form_error="Selectionnez une classe existante avant de creer l'inscription.",
            selected_level=selected_level,
            selected_class_id=academic_class_id,
        )

    amount = get_positioning_fee_for_level(candidature.programme, academic_class.level) or 0
    if amount <= 0:
        return _render_manager_academic_positioning_modal(
            request,
            candidature,
            form_error="Aucun frais n'est configure pour ce niveau dans ce programme.",
            selected_level=selected_level or academic_class.level,
            selected_class_id=academic_class_id,
        )

    try:
        from inscriptions.services import create_inscription_from_candidature

        inscription = create_inscription_from_candidature(
            candidature=candidature,
            amount_due=amount,
            academic_class=academic_class,
            status=Inscription.STATUS_AWAITING_PAYMENT,
        )
    except Exception as e:
        return _render_manager_academic_positioning_modal(
            request,
            candidature,
            form_error=str(e),
            selected_level=selected_level or getattr(academic_class, "level", ""),
            selected_class_id=academic_class_id,
        )

    response = HttpResponse("")
    response["HX-Trigger"] = (
        '{"inscriptionCreated": {"candidature_id": %s, "inscription_id": %s}, '
        '"showToast": {"message": "Inscription creee avec succes.", "type": "success"}}'
        % (candidature.id, inscription.id)
    )
    return response
