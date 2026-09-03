from django.db.models import Q, QuerySet
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.text import slugify
from django.views.decorators.http import require_GET

from admissions.models import Candidature
from accounts.models import (
    BranchBankTransfer,
    BranchExpense,
    Donation,
    PayrollEntry,
    Profile,
    TeacherHonorariumEntry,
)
from inscriptions.models import Inscription
from payments.models import Payment

from accounts.dashboards.htmx_utils import manager_required
from accounts.services.donation_pdf import build_donation_receipt
from accounts.services.financial_reports import render_manager_financial_report_pdf
from accounts.services.payslip_pdf import (
    build_honorarium_pdf,
    build_payroll_pdf,
    build_teacher_service_sheet_pdf,
)
from core.pdf_documents import generate_pdf as generate_esfe_pdf


def _pdf_response(pdf_bytes: bytes, filename: str) -> HttpResponse:
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Content-Length"] = len(pdf_bytes)
    return response


def _media_pdf_response(field_file, *, filename: str) -> FileResponse:
    if not field_file or not field_file.name.lower().endswith(".pdf"):
        raise Http404("Document PDF indisponible.")
    return FileResponse(
        field_file.open("rb"),
        as_attachment=True,
        filename=filename,
        content_type="application/pdf",
    )


def _document_reference(value, fallback: str) -> str:
    return slugify(str(value)) or fallback


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
def inscription_sheet_pdf(request: HttpRequest, pk: int) -> HttpResponse:
    inscription = get_object_or_404(
        Inscription.objects.select_related(
            "candidature__branch",
            "candidature__programme",
            "candidature__programme__cycle",
            "academic_class",
        ),
        pk=pk,
        candidature__branch=request.branch,
        candidature__is_deleted=False,
        is_archived=False,
    )
    candidature = inscription.candidature
    programme = candidature.programme
    pdf_bytes = generate_esfe_pdf(
        "esfe_inscription_certificate",
        {
            "student_name": candidature.full_name,
            "student_matricule": inscription.public_token,
            "student_birth": candidature.birth_date.strftime("%d/%m/%Y"),
            "student_phone": candidature.phone,
            "programme": programme.title if programme else "",
            "level": inscription.academic_level or (
                inscription.academic_class.level if inscription.academic_class_id else ""
            ),
            "branch_name": request.branch.name,
            "academic_year": candidature.academic_year,
            "inscription_date": inscription.created_at.strftime("%d/%m/%Y"),
        },
        request=request,
    )
    reference = _document_reference(inscription.public_token, str(inscription.pk))
    return _pdf_response(pdf_bytes, f"fiche-inscription-{reference}.pdf")


@manager_required
@require_GET
def payment_receipt_pdf(request: HttpRequest, pk: int) -> FileResponse:
    payment = get_object_or_404(
        Payment.objects.select_related("inscription__candidature"),
        pk=pk,
        inscription__candidature__branch=request.branch,
        status=Payment.STATUS_VALIDATED,
    )
    reference = _document_reference(payment.receipt_number or payment.reference, str(payment.pk))
    return _media_pdf_response(payment.receipt_pdf, filename=f"recu-{reference}.pdf")


@manager_required
@require_GET
def payroll_sheet_pdf(request: HttpRequest, pk: int) -> HttpResponse:
    entry = get_object_or_404(
        PayrollEntry.objects.select_related("employee__profile", "branch"),
        pk=pk,
        branch=request.branch,
    )
    return _pdf_response(
        build_payroll_pdf(entry),
        f"fiche-paie-{entry.period_month:%Y-%m}-{entry.pk}.pdf",
    )


@manager_required
@require_GET
def honorarium_statement_pdf(request: HttpRequest, pk: int) -> HttpResponse:
    entry = get_object_or_404(
        TeacherHonorariumEntry.objects.select_related("teacher__profile", "branch"),
        pk=pk,
        branch=request.branch,
    )
    return _pdf_response(
        build_honorarium_pdf(entry),
        f"bordereau-honoraires-{entry.period_month:%Y-%m}-{entry.pk}.pdf",
    )


@manager_required
@require_GET
def teacher_service_sheet_pdf(request: HttpRequest, pk: int) -> HttpResponse:
    entry = get_object_or_404(
        TeacherHonorariumEntry.objects.select_related("teacher__profile", "branch"),
        pk=pk,
        branch=request.branch,
    )
    return _pdf_response(
        build_teacher_service_sheet_pdf(entry),
        f"fiche-service-{entry.period_month:%Y-%m}-{entry.pk}.pdf",
    )


@manager_required
@require_GET
def donation_receipt_pdf(request: HttpRequest, pk: int) -> HttpResponse:
    donation = get_object_or_404(
        Donation.objects.select_related("branch"),
        pk=pk,
        branch=request.branch,
    )
    reference = _document_reference(donation.receipt_number or donation.pk, str(donation.pk))
    return _pdf_response(build_donation_receipt(donation), f"recu-don-{reference}.pdf")


@manager_required
@require_GET
def expense_supporting_document_pdf(request: HttpRequest, pk: int) -> FileResponse:
    expense = get_object_or_404(BranchExpense, pk=pk, branch=request.branch)
    reference = _document_reference(expense.reference or expense.pk, str(expense.pk))
    return _media_pdf_response(
        expense.receipt,
        filename=f"piece-justificative-{reference}.pdf",
    )


@manager_required
@require_GET
def bank_transfer_slip_pdf(request: HttpRequest, pk: int) -> FileResponse:
    transfer = get_object_or_404(BranchBankTransfer, pk=pk, branch=request.branch)
    reference = _document_reference(transfer.reference, str(transfer.pk))
    return _media_pdf_response(
        transfer.proof,
        filename=f"bordereau-versement-{reference}.pdf",
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
        cash_type=(request.GET.get("cash_type") or "").strip(),
        cash_source=(request.GET.get("cash_source") or "").strip(),
    )
    label = report_period["label"].replace(" ", "_")
    return xlsx_response(
        wb,
        filename=f"rapport_{branch.code}_{label}_{today.isoformat()}.xlsx",
    )


@manager_required
@require_GET
def export_report_pdf(request: HttpRequest) -> HttpResponse:
    branch = request.branch
    pdf_bytes = render_manager_financial_report_pdf(branch=branch, request=request)
    from accounts.services.financial_reports import resolve_financial_report_period

    report_period = resolve_financial_report_period(request)
    label = _document_reference(report_period["label"], "periode")
    branch_code = _document_reference(branch.code, str(branch.pk))
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="etat-financier-{branch_code}-{label}.pdf"'
    )
    response["Content-Length"] = len(pdf_bytes)
    return response
