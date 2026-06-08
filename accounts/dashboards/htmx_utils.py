from collections.abc import Callable
from datetime import date
from typing import Any

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import AbstractBaseUser
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone

from academics.services.academic_positioning import get_positioning_context
from accounts.models import Profile
from branches.models import Branch
from inscriptions.models import Inscription
from payments.models import CashPaymentSession, PaymentAgent


PAYABLE_INSCRIPTION_STATUSES: set[str] = {
    Inscription.STATUS_CREATED,
    Inscription.STATUS_AWAITING_PAYMENT,
    Inscription.STATUS_PARTIAL,
}


def manager_required(view_func: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        from accounts.dashboards.helpers import is_manager, get_user_branch

        if not is_manager(request.user):
            return HttpResponse("Non autorise", status=403)
        branch = get_user_branch(request.user)
        if not branch:
            return HttpResponse("Annexe non trouvee", status=403)
        request.branch = branch
        return view_func(request, *args, **kwargs)

    return login_required(wrapper)


def get_current_agent(user: AbstractBaseUser, branch: Branch) -> PaymentAgent | None:
    return (
        PaymentAgent.objects
        .select_related("user", "branch")
        .filter(user=user, branch=branch, is_active=True)
        .first()
    )


def _render_manager_academic_positioning_modal(
    request: HttpRequest,
    candidature: Any,
    *,
    form_error: str = "",
    selected_level: str = "",
    selected_class_id: str = "",
) -> HttpResponse:
    return render(
        request,
        "accounts/dashboard/partials/academic_positioning_body.html",
        {
            "candidature": candidature,
            "positioning": get_positioning_context(candidature=candidature),
            "form_error": form_error,
            "selected_level": (selected_level or "").strip().upper(),
            "selected_class_id": str(selected_class_id or "").strip(),
            "submit_url_name": "accounts:htmx_inscription_create",
        },
    )


def get_active_cash_session(inscription: Inscription) -> CashPaymentSession | None:
    return (
        CashPaymentSession.objects
        .filter(
            inscription=inscription,
            is_used=False,
            expires_at__gt=timezone.now(),
        )
        .select_related(
            "agent__user",
            "inscription",
            "inscription__candidature",
            "inscription__candidature__programme",
        )
        .order_by("-created_at")
        .first()
    )


def get_salary_period_from_request(request: HttpRequest) -> date:
    raw_value = (request.GET.get("salary_month") or request.POST.get("period_month") or "").strip()
    if raw_value:
        try:
            return date.fromisoformat(f"{raw_value[:7]}-01")
        except ValueError:
            pass
    today = timezone.now().date()
    return today.replace(day=1)


def get_branch_staff_profile(branch: Branch, user_id: int) -> Profile:
    return get_object_or_404(
        Profile.objects.select_related("user", "branch").filter(
            branch=branch,
            user__is_active=True,
        ).exclude(position="student").exclude(user_type="public"),
        user_id=user_id,
    )


def get_branch_teacher_profile(branch: Branch, user_id: int) -> Profile:
    profile = get_branch_staff_profile(branch, user_id)
    if profile.position != "teacher":
        from django.http import Http404
        raise Http404("Profil enseignant introuvable")
    return profile


def manager_salary_redirect_response(period_month: date) -> HttpResponse:
    response = HttpResponse("")
    response["HX-Redirect"] = (
        f"{reverse('accounts:manager_dashboard')}?section=salaires&salary_month={period_month.strftime('%Y-%m')}"
    )
    return response


def manager_closure_redirect_response(period_month: date) -> HttpResponse:
    response = HttpResponse("")
    response["HX-Redirect"] = (
        f"{reverse('accounts:manager_dashboard')}?section=cloture&salary_month={period_month.strftime('%Y-%m')}"
    )
    return response


def manager_section_redirect_response(section: str) -> HttpResponse:
    response = HttpResponse("")
    response["HX-Redirect"] = f"{reverse('accounts:manager_dashboard')}?section={section}"
    return response


def manager_section_notice_redirect_response(section: str, message: str) -> HttpResponse:
    response = HttpResponse("")
    response["HX-Redirect"] = f"{reverse('accounts:manager_dashboard')}?section={section}&notice={message}"
    return response
