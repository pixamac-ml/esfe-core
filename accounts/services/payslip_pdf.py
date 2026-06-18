from django.core.files.base import ContentFile
from django.utils.dateformat import format as date_format

from core.pdf_documents import generate_pdf as generate_esfe_pdf


def build_payroll_pdf(entry):
    employee = entry.employee
    allowances = []
    if entry.allowances:
        allowances.append({"label": "Indemnites", "amount": f"{entry.allowances:,} FCFA".replace(",", " ")})
    deductions = []
    if entry.deductions:
        deductions.append({"label": "Retenues diverses", "amount": f"{entry.deductions:,} FCFA".replace(",", " ")})

    pdf_bytes = generate_esfe_pdf("esfe_salary_slip", {
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
    })
    return pdf_bytes


def build_honorarium_pdf(entry):
    teacher = entry.teacher
    deductions = []
    if entry.deductions:
        deductions.append({"label": "Retenues diverses", "amount": f"{entry.deductions:,} FCFA".replace(",", " ")})

    pdf_bytes = generate_esfe_pdf("esfe_salary_slip", {
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
    })
    return pdf_bytes


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
