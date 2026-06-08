from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.template.loader import render_to_string


TEMPLATE_MAP = {
    "esfe_document_base": "documents/base_document/base_document.html",
    "esfe_receipt": "documents/payment_receipt/payment_receipt.html",
    "esfe_shop_invoice": "documents/shop_invoice/shop_invoice.html",
    "esfe_salary_slip": "documents/salary_slip/salary_slip.html",
    "esfe_refund": "documents/refund_document/refund_document.html",
    "esfe_cash_receipt": "documents/cash_receipt/cash_receipt.html",
    "esfe_donation_receipt": "documents/donation_receipt/donation_receipt.html",
    "esfe_inscription_certificate": "documents/inscription_certificate/inscription_certificate.html",
}


def _resolve_logo_url():
    logo_path = finders.find("institution/logo_esfe.png")
    if logo_path:
        return Path(logo_path).resolve().as_uri()
    return ""


def _get_template_name(component_name):
    name = TEMPLATE_MAP.get(component_name)
    if not name:
        raise ValueError(f"Unknown document component: {component_name}")
    return name


def _render_html(component_name, context, request=None):
    if "logo_url" not in context:
        context = {**context, "logo_url": _resolve_logo_url()}
    return render_to_string(
        _get_template_name(component_name), context, request=request
    )


def generate_pdf(component_name, context, request=None):
    html_string = _render_html(component_name, context, request=request)
    try:
        from weasyprint import HTML

        if request:
            base_url = request.build_absolute_uri()
        else:
            base_url = _resolve_logo_url().rsplit("/", 1)[0] if _resolve_logo_url() else None

        return HTML(string=html_string, base_url=base_url).write_pdf()
    except ImportError:
        raise RuntimeError("weasyprint not installed") from None


def generate_pdf_response(component_name, context, filename="document.pdf", request=None):
    from django.http import HttpResponse

    pdf_bytes = generate_pdf(component_name, context, request=request)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Content-Length"] = len(pdf_bytes)
    return response
