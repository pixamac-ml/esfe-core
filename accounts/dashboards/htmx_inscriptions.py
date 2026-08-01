import json

from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from academics.models import AcademicClass
from academics.services.academic_positioning import get_positioning_fee_for_level
from admissions.models import Candidature
from coupons.services.application import apply_coupon
from coupons.services.validation import get_valid_coupon
from inscriptions.models import Inscription

from accounts.dashboards.htmx_utils import (
    PAYABLE_INSCRIPTION_STATUSES,
    _render_manager_academic_positioning_modal,
    get_active_cash_session,
    get_current_agent,
    manager_required,
)


def _get_manager_inscription(request: HttpRequest, pk: int) -> Inscription:
    return get_object_or_404(
        Inscription.objects.select_related(
            "candidature",
            "candidature__programme",
            "candidature__branch",
        ).prefetch_related("payments"),
        pk=pk,
        candidature__branch=request.branch,
    )


def _build_inscription_detail_context(request: HttpRequest, inscription: Inscription, *, coupon_error: str = "") -> dict:
    manager_agent = get_current_agent(request.user, request.branch)
    active_cash_session = get_active_cash_session(inscription)
    return {
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
        "can_apply_coupon": (
            not inscription.is_paid
            and not hasattr(inscription, "coupon_redemption")
            and inscription.status not in [Inscription.STATUS_CANCELLED, Inscription.STATUS_EXPIRED]
        ),
        "existing_coupon_redemption": getattr(inscription, "coupon_redemption", None),
        "coupon_error": coupon_error,
    }


@manager_required
@require_GET
def inscription_detail(request: HttpRequest, pk: int) -> HttpResponse:
    inscription = _get_manager_inscription(request, pk)
    return render(
        request,
        "accounts/dashboard/partials/inscription_modal.html",
        _build_inscription_detail_context(request, inscription),
    )


@manager_required
@require_POST
def inscription_apply_coupon(request: HttpRequest, pk: int) -> HttpResponse:
    inscription = _get_manager_inscription(request, pk)
    code = (request.POST.get("coupon_code") or "").strip()
    coupon_error = ""
    redemption = None
    try:
        redemption = apply_coupon(
            code=code,
            inscription_id=inscription.id,
            actor=request.user,
            branch=request.branch,
        )
        inscription.refresh_from_db()
    except ValidationError as exc:
        coupon_error = exc.messages[0] if hasattr(exc, "messages") else str(exc)

    response = render(
        request,
        "accounts/dashboard/partials/inscription_modal.html",
        _build_inscription_detail_context(request, inscription, coupon_error=coupon_error),
    )
    if redemption is not None:
        response["HX-Trigger"] = json.dumps({
            "couponApplied": {
                "inscription_id": inscription.id,
                "discount_amount": redemption.discount_amount,
                "amount_after": redemption.amount_after,
            },
            "showToast": {
                "message": (
                    f"Coupon {redemption.coupon.code} appliqué : "
                    f"réduction de {redemption.discount_amount} FCFA."
                ),
                "type": "success",
            },
        })
    elif coupon_error:
        response["HX-Trigger"] = json.dumps({
            "showToast": {"message": coupon_error, "type": "error"},
        })
    return response


@manager_required
@require_GET
def coupon_preview(request: HttpRequest) -> HttpResponse:
    inscription_id = (request.GET.get("inscription_id") or "").strip()
    code = (request.GET.get("code") or "").strip()
    if not inscription_id.isdigit():
        return render(
            request,
            "accounts/dashboard/partials/coupon_preview.html",
            {"valid": False, "message": "Inscription invalide."},
            status=400,
        )
    inscription = get_object_or_404(
        Inscription.objects.select_related("candidature", "candidature__programme", "candidature__branch"),
        pk=inscription_id,
        candidature__branch=request.branch,
    )
    try:
        coupon = get_valid_coupon(code, inscription)
    except ValidationError as exc:
        message = exc.messages[0] if hasattr(exc, "messages") else str(exc)
        return render(
            request,
            "accounts/dashboard/partials/coupon_preview.html",
            {"valid": False, "message": message},
        )

    discount = coupon.compute_discount(inscription.amount_due)
    new_amount = max(inscription.amount_due - discount, inscription.amount_paid)
    actual_discount = inscription.amount_due - new_amount
    return render(
        request,
        "accounts/dashboard/partials/coupon_preview.html",
        {
            "valid": True,
            "coupon": coupon,
            "discount": actual_discount,
            "new_amount": new_amount,
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
        .filter(pk=academic_class_id, branch=request.branch)
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

    coupon_code = (request.POST.get("coupon_code") or "").strip()
    coupon_warning = ""
    if coupon_code:
        try:
            apply_coupon(
                code=coupon_code,
                inscription_id=inscription.id,
                actor=request.user,
                branch=request.branch,
            )
            inscription.refresh_from_db(fields=["amount_due"])
        except ValidationError as exc:
            coupon_warning = exc.messages[0] if hasattr(exc, "messages") else str(exc)

    if coupon_warning:
        toast = {
            "message": f"Inscription creee, mais le coupon n'a pas pu etre applique : {coupon_warning}",
            "type": "warning",
        }
    elif coupon_code:
        toast = {
            "message": f"Inscription creee avec succes. Montant apres reduction : {inscription.amount_due} FCFA.",
            "type": "success",
        }
    else:
        toast = {"message": "Inscription creee avec succes.", "type": "success"}

    response = HttpResponse("")
    response["HX-Trigger"] = json.dumps(
        {
            "inscriptionCreated": {"candidature_id": candidature.id, "inscription_id": inscription.id},
            "showToast": toast,
        }
    )
    return response
