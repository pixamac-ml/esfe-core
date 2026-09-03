from datetime import datetime

from django.core.files.base import ContentFile
from django.utils.dateformat import format as date_format

from academics.models import LessonLog
from accounts.models import PaymentSignatureSession

from core.pdf_documents import generate_pdf as generate_esfe_pdf


def _signature_context(*, entry, entry_field):
    session = (
        PaymentSignatureSession.objects
        .filter(**{entry_field: entry, "status": PaymentSignatureSession.STATUS_COMPLETED})
        .order_by("-completed_at", "-pk")
        .first()
    )
    if not session:
        return {
            "signature_data": "",
            "signature_name": "",
            "signature_date": "",
            "signature_hash_short": "",
        }
    return {
        "signature_data": session.signature_data,
        "signature_name": session.beneficiary.get_full_name() or session.beneficiary.username,
        "signature_date": session.signed_at.strftime("%d/%m/%Y %H:%M") if session.signed_at else "",
        "signature_hash_short": session.signature_sha256[:16],
    }


def build_payroll_pdf(entry):
    employee = entry.employee
    allowances = []
    if entry.allowances:
        allowances.append({"label": "Indemnites", "amount": f"{entry.allowances:,} FCFA".replace(",", " ")})
    deductions = []
    if entry.deductions:
        deductions.append({"label": "Retenues diverses", "amount": f"{entry.deductions:,} FCFA".replace(",", " ")})

    context = {
        "slip_number": f"SAL-{entry.period_month}-{entry.employee_id:04d}",
        "date": entry.created_at.strftime("%d %B %Y"),
        "period": date_format(entry.period_month, "F Y"),
        "employee_name": employee.get_full_name() if hasattr(employee, "get_full_name") else str(employee),
        "employee_position": getattr(employee.profile, "position", "") if hasattr(employee, "profile") else "",
        "employee_matricule": getattr(employee, "username", str(employee.id)),
        "base_salary": f"{entry.base_salary:,} FCFA".replace(",", " "),
        "allowances": allowances,
        "deductions": deductions,
        "advances": f"{entry.advances:,}".replace(",", " ") if entry.advances else "0",
        "net_salary": f"{entry.net_salary:,}".replace(",", " "),
        "paid_amount": f"{entry.paid_amount:,} FCFA".replace(",", " ") if entry.paid_amount else "0 FCFA",
        "remaining": f"{entry.remaining_salary:,} FCFA".replace(",", " ") if entry.remaining_salary else "0 FCFA",
        "status": entry.status,
    }
    context.update(_signature_context(entry=entry, entry_field="payroll_entry"))
    pdf_bytes = generate_esfe_pdf("esfe_salary_slip", context)
    return pdf_bytes


def build_honorarium_pdf(entry):
    teacher = entry.teacher
    deductions = []
    if entry.deductions:
        deductions.append({"label": "Retenues diverses", "amount": f"{entry.deductions:,} FCFA".replace(",", " ")})

    context = {
        "slip_number": f"HON-{entry.period_month}-{entry.teacher_id:04d}",
        "date": entry.created_at.strftime("%d %B %Y"),
        "period": date_format(entry.period_month, "F Y"),
        "employee_name": teacher.get_full_name() if hasattr(teacher, "get_full_name") else str(teacher),
        "employee_position": "Enseignant",
        "employee_matricule": getattr(teacher, "username", str(teacher.id)),
        "base_salary": f"{entry.validated_hours} h × {entry.hourly_rate:,} FCFA/h".replace(",", " ")
            + (f" + {entry.adjustments:,} FCFA ajust.".replace(",", " ") if entry.adjustments else ""),
        "allowances": [],
        "deductions": deductions,
        "advances": f"{entry.advances:,}".replace(",", " ") if entry.advances else "0",
        "net_salary": f"{entry.net_amount:,}".replace(",", " "),
        "paid_amount": f"{entry.paid_amount:,} FCFA".replace(",", " ") if entry.paid_amount else "0 FCFA",
        "remaining": f"{entry.net_amount - entry.paid_amount:,} FCFA".replace(",", " ") if entry.net_amount > (entry.paid_amount or 0) else "0 FCFA",
        "status": entry.status,
    }
    context.update(_signature_context(entry=entry, entry_field="honorarium_entry"))
    pdf_bytes = generate_esfe_pdf("esfe_salary_slip", context)
    return pdf_bytes


def build_teacher_service_sheet_pdf(entry):
    """Generate the teacher's service sheet from validated lesson logs only."""
    logs = list(
        LessonLog.objects.filter(
            branch=entry.branch,
            teacher=entry.teacher,
            date__year=entry.period_month.year,
            date__month=entry.period_month.month,
            status=LessonLog.STATUS_DONE,
            validated_by__isnull=False,
        )
        .select_related("academic_class", "ec", "validated_by")
        .order_by("date", "start_time", "pk")
    )
    rows = []
    for log in logs:
        start = datetime.combine(entry.period_month, log.start_time)
        end = datetime.combine(entry.period_month, log.end_time)
        duration_minutes = max(int((end - start).total_seconds() // 60), 0)
        rows.append({
            "date": log.date.strftime("%d/%m/%Y"),
            "academic_class": str(log.academic_class),
            "ec": str(log.ec),
            "time": f"{log.start_time:%H:%M} - {log.end_time:%H:%M}",
            "hours": f"{duration_minutes // 60} h {duration_minutes % 60:02d}",
            "validator": log.validated_by.get_full_name() or log.validated_by.username,
        })
    teacher = entry.teacher
    return generate_esfe_pdf("esfe_teacher_service_sheet", {
        "reference": f"SVC-{entry.period_month:%Y%m}-{entry.teacher_id:04d}",
        "period": date_format(entry.period_month, "F Y"),
        "generated_at": entry.updated_at.strftime("%d/%m/%Y %H:%M"),
        "branch_name": entry.branch.name,
        "teacher_name": teacher.get_full_name() or teacher.username,
        "teacher_matricule": getattr(teacher, "username", str(teacher.pk)),
        "hourly_rate": f"{entry.hourly_rate:,}".replace(",", " "),
        "validated_hours": str(entry.validated_hours),
        "estimated_amount": f"{entry.net_amount:,}".replace(",", " "),
        "rows": rows,
    })


def ensure_payroll_receipt(entry):
    if entry.status in ("paid", "partial") and getattr(entry, "receipt_pdf", None):
        return entry.receipt_pdf
    pdf_bytes = build_payroll_pdf(entry)
    filename = f"paie-{entry.period_month}-{entry.employee_id:04d}.pdf"
    if hasattr(entry, "receipt_pdf"):
        entry.receipt_pdf.save(filename, ContentFile(pdf_bytes), save=True)
    return pdf_bytes


def ensure_honorarium_receipt(entry):
    if entry.status in ("paid", "partial") and getattr(entry, "receipt_pdf", None):
        return entry.receipt_pdf
    pdf_bytes = build_honorarium_pdf(entry)
    filename = f"honoraire-{entry.period_month}-{entry.teacher_id:04d}.pdf"
    if hasattr(entry, "receipt_pdf"):
        entry.receipt_pdf.save(filename, ContentFile(pdf_bytes), save=True)
    return pdf_bytes
