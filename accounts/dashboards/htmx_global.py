from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from admissions.models import Candidature
from accounts.models import Profile
from inscriptions.models import Inscription
from payments.models import Payment

from accounts.dashboards.htmx_utils import manager_required


@manager_required
@require_GET
def global_search(request: HttpRequest) -> HttpResponse:
    q: str = request.GET.get("q", "").strip()
    branch = request.branch

    if len(q) < 2:
        return HttpResponse("")

    candidatures: QuerySet[Candidature] = Candidature.objects.filter(
        branch=branch,
        is_deleted=False,
    ).filter(
        Q(first_name__icontains=q)
        | Q(last_name__icontains=q)
        | Q(email__icontains=q)
    )[:5]
    inscriptions: QuerySet[Inscription] = Inscription.objects.filter(
        candidature__branch=branch,
        candidature__is_deleted=False,
        is_archived=False,
    ).filter(
        Q(candidature__first_name__icontains=q)
        | Q(candidature__last_name__icontains=q)
        | Q(public_token__icontains=q)
    ).select_related("candidature")[:5]
    payments: QuerySet[Payment] = Payment.objects.filter(
        inscription__candidature__branch=branch,
        inscription__candidature__is_deleted=False,
        inscription__is_archived=False,
    ).filter(
        Q(reference__icontains=q)
        | Q(inscription__candidature__last_name__icontains=q)
    ).select_related("inscription__candidature")[:5]

    return render(
        request,
        "accounts/dashboard/partials/search_results.html",
        {
            "candidatures": candidatures,
            "inscriptions": inscriptions,
            "payments": payments,
            "query": q,
        },
    )


@manager_required
@require_GET
def export_report_xlsx(request: HttpRequest) -> HttpResponse:
    from datetime import date
    from accounts.dashboards.manager_dashboard import _resolve_report_period
    from accounts.services.excel_reports import export_branch_report_xlsx, xlsx_response

    branch = request.branch
    today = date.today()
    report_period = _resolve_report_period(request, today)

    branch_staff_profiles: QuerySet[Profile] = Profile.objects.filter(
        branch=branch, user__is_active=True,
    ).exclude(position="student").exclude(user_type="public").order_by("user__first_name")[:500]

    branch_teacher_profiles: QuerySet[Profile] = Profile.objects.filter(
        branch=branch, user__is_active=True, position="teacher",
    ).exclude(user_type="public").order_by("user__first_name")[:500]

    wb = export_branch_report_xlsx(
        branch=branch,
        report_period=report_period,
        branch_staff_profiles=branch_staff_profiles,
        branch_teacher_profiles=branch_teacher_profiles,
    )
    label = report_period["label"].replace(" ", "_")
    return xlsx_response(
        wb,
        filename=f"rapport_{branch.code}_{label}_{today.isoformat()}.xlsx",
    )
