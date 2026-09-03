from calendar import month_name, monthrange
from datetime import date, timedelta
from io import BytesIO

from django.db.models import Count, Q, Sum
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from accounts.models import BranchCashMovement
from accounts.services.manager_intelligence import (
    branch_financial_orphan_report,
    get_branch_cash_balance,
)


MONTH_LABELS = [
    ("1", "Janvier"),
    ("2", "Fevrier"),
    ("3", "Mars"),
    ("4", "Avril"),
    ("5", "Mai"),
    ("6", "Juin"),
    ("7", "Juillet"),
    ("8", "Aout"),
    ("9", "Septembre"),
    ("10", "Octobre"),
    ("11", "Novembre"),
    ("12", "Decembre"),
]

TYPE_FILTER_CHOICES = [
    ("", "Tous les types"),
    (BranchCashMovement.TYPE_IN, "Recettes"),
    (BranchCashMovement.TYPE_OUT, "Depenses"),
]


def _money(value):
    return f"{value or 0:,} FCFA".replace(",", " ")


def _month_label(year, month):
    french_months = {
        1: "Janvier",
        2: "Fevrier",
        3: "Mars",
        4: "Avril",
        5: "Mai",
        6: "Juin",
        7: "Juillet",
        8: "Aout",
        9: "Septembre",
        10: "Octobre",
        11: "Novembre",
        12: "Decembre",
    }
    return f"{french_months.get(month, month_name[month]).strip()} {year}"


def resolve_financial_report_period(request, today=None):
    today = today or timezone.localdate()
    preset = (request.GET.get("report_period") or "month").strip()
    start_raw = (request.GET.get("report_start") or "").strip()
    end_raw = (request.GET.get("report_end") or "").strip()
    month_raw = (request.GET.get("report_month") or "").strip()
    year_raw = (request.GET.get("report_year") or "").strip()

    if month_raw or year_raw:
        try:
            month = int(month_raw) if month_raw else today.month
            year = int(year_raw) if year_raw else today.year
            start_date = date(year, month, 1)
            end_date = date(year, month, monthrange(year, month)[1])
        except ValueError:
            month = today.month
            year = today.year
            start_date = today.replace(day=1)
            end_date = today
        return {
            "preset": "month",
            "start": start_date,
            "end": end_date,
            "label": _month_label(year, month),
            "month": month,
            "year": year,
        }

    period_map = {
        "today": (today, today, "Aujourd'hui"),
        "yesterday": (today - timedelta(days=1), today - timedelta(days=1), "Hier"),
        "week": (today - timedelta(days=6), today, "Cette semaine glissante"),
        "two_weeks": (today - timedelta(days=13), today, "Deux semaines"),
        "month": (today.replace(day=1), today, "Ce mois"),
        "three_months": (today - timedelta(days=89), today, "Trois mois"),
        "semester": (today - timedelta(days=179), today, "Semestre"),
        "year": (today.replace(month=1, day=1), today, "Cette annee"),
    }

    if preset == "custom":
        try:
            start_date = date.fromisoformat(start_raw)
            end_date = date.fromisoformat(end_raw)
        except ValueError:
            start_date = today.replace(day=1)
            end_date = today
            preset = "month"
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        return {
            "preset": preset,
            "start": start_date,
            "end": end_date,
            "label": "Periode personnalisee",
            "month": start_date.month,
            "year": start_date.year,
        }

    start_date, end_date, label = period_map.get(preset, period_map["month"])
    return {
        "preset": preset,
        "start": start_date,
        "end": end_date,
        "label": label,
        "month": start_date.month,
        "year": start_date.year,
    }


def _branch_source_value(source_rows, source, key):
    row = source_rows.get(source, {})
    return row.get(key, 0) or 0


def build_manager_financial_report_context(*, branch, request, today=None):
    today = today or timezone.localdate()
    report_period = resolve_financial_report_period(request, today=today)
    cash_type = (request.GET.get("cash_type") or "").strip()
    cash_source = (request.GET.get("cash_source") or "").strip()
    report_branch = branch
    from coupons.models import CouponRedemption

    coupon_redemptions = CouponRedemption.objects.filter(
        inscription__candidature__branch=report_branch,
        applied_at__date__gte=report_period["start"],
        applied_at__date__lte=report_period["end"],
    )
    coupon_redemptions_count = coupon_redemptions.count()
    coupon_discount_total = coupon_redemptions.aggregate(
        total=Sum("discount_amount")
    )["total"] or 0

    report_movements = BranchCashMovement.objects.filter(
        branch=report_branch,
        movement_date__gte=report_period["start"],
        movement_date__lte=report_period["end"],
    )
    if cash_type:
        report_movements = report_movements.filter(movement_type=cash_type)
    if cash_source:
        report_movements = report_movements.filter(source=cash_source)

    movement_count = report_movements.count()
    movement_preview = report_movements.select_related("created_by", "expense").order_by("-movement_date", "-created_at")[:20]

    source_rows_map = {
        source: {
            "source": source,
            "label": label,
            "in_total": 0,
            "out_total": 0,
            "in_count": 0,
            "out_count": 0,
        }
        for source, label in BranchCashMovement.SOURCE_CHOICES
    }
    extra_source_labels = {}
    for row in report_movements.values("source", "movement_type").annotate(total=Sum("amount"), count=Count("id")):
        source = row["source"] or BranchCashMovement.SOURCE_MANUAL
        if source not in source_rows_map:
            extra_source_labels.setdefault(source, source.replace("_", " ").title())
            source_rows_map[source] = {
                "source": source,
                "label": extra_source_labels[source],
                "in_total": 0,
                "out_total": 0,
                "in_count": 0,
                "out_count": 0,
            }
        bucket = source_rows_map[source]
        if row["movement_type"] == BranchCashMovement.TYPE_IN:
            bucket["in_total"] += row["total"] or 0
            bucket["in_count"] += row["count"] or 0
        else:
            bucket["out_total"] += row["total"] or 0
            bucket["out_count"] += row["count"] or 0

    source_rows = list(source_rows_map.values())
    source_rows.sort(key=lambda item: (item["label"], item["source"]))
    for row in source_rows:
        row["net_total"] = (row["in_total"] or 0) - (row["out_total"] or 0)

    total_receipts = report_movements.filter(movement_type=BranchCashMovement.TYPE_IN).aggregate(total=Sum("amount"))["total"] or 0
    total_expenses = report_movements.filter(movement_type=BranchCashMovement.TYPE_OUT).aggregate(total=Sum("amount"))["total"] or 0
    student_receipts = _branch_source_value(source_rows_map, BranchCashMovement.SOURCE_STUDENT_PAYMENT, "in_total")
    shop_receipts = _branch_source_value(source_rows_map, BranchCashMovement.SOURCE_SHOP, "in_total")
    donation_receipts = _branch_source_value(source_rows_map, BranchCashMovement.SOURCE_DONATION, "in_total")
    adjustment_positive = _branch_source_value(source_rows_map, BranchCashMovement.SOURCE_ADJUSTMENT, "in_total")
    adjustment_negative = _branch_source_value(source_rows_map, BranchCashMovement.SOURCE_ADJUSTMENT, "out_total")
    salary_expenses = _branch_source_value(source_rows_map, BranchCashMovement.SOURCE_PAYROLL, "out_total")
    honorarium_expenses = _branch_source_value(source_rows_map, BranchCashMovement.SOURCE_HONORARIUM, "out_total")
    branch_expenses = _branch_source_value(source_rows_map, BranchCashMovement.SOURCE_EXPENSE, "out_total")
    bank_transfers = _branch_source_value(source_rows_map, BranchCashMovement.SOURCE_BANK_TRANSFER, "out_total")

    known_receipts = student_receipts + shop_receipts + donation_receipts + adjustment_positive
    known_expenses = salary_expenses + honorarium_expenses + branch_expenses + bank_transfers + adjustment_negative
    other_receipts = max(total_receipts - known_receipts, 0)
    other_expenses = max(total_expenses - known_expenses, 0)
    refunds = 0

    available_cash_balance = get_branch_cash_balance(report_branch)
    balance_after_bank_transfer = available_cash_balance
    balance_before_closure = available_cash_balance + bank_transfers
    recommended_bank_transfer = max(balance_before_closure - float(report_branch.cash_reserve_target or 0), 0)
    if float(recommended_bank_transfer).is_integer():
        recommended_bank_transfer = int(recommended_bank_transfer)

    period_summary = {
        "student_revenue": student_receipts,
        "shop_revenue": shop_receipts,
        "donation_revenue": donation_receipts,
        "other_revenue": other_receipts,
        "adjustment_positive": adjustment_positive,
        "refunds_paid": refunds,
        "salary_paid": salary_expenses,
        "honorarium_paid": honorarium_expenses,
        "expenses_paid": branch_expenses,
        "bank_transferred": bank_transfers,
        "other_expenses": other_expenses,
        "adjustment_negative": adjustment_negative,
        "total_revenue": total_receipts,
        "total_expenses": total_expenses,
        "net_result": total_receipts - total_expenses,
        "balance_before_closure": balance_before_closure,
        "balance_after_bank_transfer": balance_after_bank_transfer,
        "available_cash_balance": available_cash_balance,
        "cash_reserve_target": float(report_branch.cash_reserve_target or 0),
        "recommended_bank_transfer": recommended_bank_transfer,
        "coupon_redemptions_count": coupon_redemptions_count,
        "coupon_discount_total": coupon_discount_total,
    }

    source_row_lookup = {
        row["source"]: row for row in source_rows
    }
    receipt_rows = [
        {
            "label": "Paiements étudiants",
            "amount": student_receipts,
            "count": source_row_lookup.get(BranchCashMovement.SOURCE_STUDENT_PAYMENT, {}).get("in_count", 0),
            "tone": "blue",
        },
        {
            "label": "Boutique",
            "amount": shop_receipts,
            "count": source_row_lookup.get(BranchCashMovement.SOURCE_SHOP, {}).get("in_count", 0),
            "tone": "violet",
        },
        {
            "label": "Dons",
            "amount": donation_receipts,
            "count": source_row_lookup.get(BranchCashMovement.SOURCE_DONATION, {}).get("in_count", 0),
            "tone": "emerald",
        },
        {
            "label": "Autres entrees",
            "amount": other_receipts,
            "count": 0,
            "tone": "slate",
        },
        {
            "label": "Ajustements positifs",
            "amount": adjustment_positive,
            "count": source_row_lookup.get(BranchCashMovement.SOURCE_ADJUSTMENT, {}).get("in_count", 0),
            "tone": "amber",
        },
    ]
    expense_rows = [
        {
            "label": "Salaires",
            "amount": salary_expenses,
            "count": source_row_lookup.get(BranchCashMovement.SOURCE_PAYROLL, {}).get("out_count", 0),
            "tone": "rose",
        },
        {
            "label": "Honoraires enseignants",
            "amount": honorarium_expenses,
            "count": source_row_lookup.get(BranchCashMovement.SOURCE_HONORARIUM, {}).get("out_count", 0),
            "tone": "indigo",
        },
        {
            "label": "Depenses",
            "amount": branch_expenses,
            "count": source_row_lookup.get(BranchCashMovement.SOURCE_EXPENSE, {}).get("out_count", 0),
            "tone": "amber",
        },
        {
            "label": "Remboursements",
            "amount": refunds,
            "count": 0,
            "tone": "slate",
        },
        {
            "label": "Versements bancaires",
            "amount": bank_transfers,
            "count": source_row_lookup.get(BranchCashMovement.SOURCE_BANK_TRANSFER, {}).get("out_count", 0),
            "tone": "blue",
        },
        {
            "label": "Autres sorties",
            "amount": other_expenses,
            "count": 0,
            "tone": "slate",
        },
        {
            "label": "Ajustements negatifs",
            "amount": adjustment_negative,
            "count": source_row_lookup.get(BranchCashMovement.SOURCE_ADJUSTMENT, {}).get("out_count", 0),
            "tone": "rose",
        },
    ]

    orphan_period_month = report_period["start"].replace(day=1)
    orphan_report = branch_financial_orphan_report(branch, period_month=orphan_period_month)
    orphan_count = sum(len(items) for items in orphan_report.values())
    bank_transfer_overage = max(bank_transfers - balance_before_closure, 0)
    alerts = []
    if orphan_count:
        alerts.append({
            "level": "danger",
            "title": "Operations orphelines",
            "message": f"{orphan_count} operation(s) financiere(s) sans mouvement de caisse coherent.",
        })
    if available_cash_balance < 0:
        alerts.append({
            "level": "danger",
            "title": "Caisse negative",
            "message": "Le solde reel de caisse est negatif.",
        })
    if bank_transfer_overage > 0:
        alerts.append({
            "level": "warning",
            "title": "Versement bancaire excessif",
            "message": "Le versement bancaire cumule depasse le solde disponible avant cloture.",
        })

    closure_possible = not alerts
    closure_blockers = [alert["message"] for alert in alerts if alert["level"] == "danger"]

    return {
        "report_period": report_period,
        "report_branch": report_branch,
        "report_branch_label": report_branch.name,
        "report_branch_locked": True,
        "report_month_options": MONTH_LABELS,
        "report_year_options": [str(year) for year in range(today.year - 3, today.year + 2)],
        "report_type_options": TYPE_FILTER_CHOICES,
        "report_source_options": [("", "Toutes les sources"), *BranchCashMovement.SOURCE_CHOICES],
        "report_cash_type": cash_type,
        "report_cash_source": cash_source,
        "report_movements": movement_preview,
        "report_movements_count": movement_count,
        "report_source_rows": source_rows,
        "report_receipt_rows": receipt_rows,
        "report_expense_rows": expense_rows,
        "report_summary": period_summary,
        "report_alerts": alerts,
        "report_orphan_report": orphan_report,
        "report_closure_possible": closure_possible,
        "report_closure_blockers": closure_blockers,
        "report_available_cash_balance": available_cash_balance,
        "report_recommended_bank_transfer": recommended_bank_transfer,
        "report_balance_before_closure": balance_before_closure,
        "report_balance_after_bank_transfer": balance_after_bank_transfer,
        "report_bank_transfer_total": bank_transfers,
        "report_bank_transfer_overage": bank_transfer_overage,
        "report_reserve_target": float(report_branch.cash_reserve_target or 0),
        "report_generated_at": timezone.now(),
        "report_has_filters": bool(cash_type or cash_source or request.GET.get("report_month") or request.GET.get("report_year")),
        "report_summary_rows": [
            {"label": "Total recettes", "amount": total_receipts, "tone": "emerald"},
            {"label": "Total depenses", "amount": total_expenses, "tone": "rose"},
            {"label": "Resultat net", "amount": total_receipts - total_expenses, "tone": "primary"},
            {"label": "Montant deja verse en banque", "amount": bank_transfers, "tone": "blue"},
            {"label": "Reste reel en caisse", "amount": available_cash_balance, "tone": "slate"},
            {"label": "Solde avant cloture", "amount": balance_before_closure, "tone": "amber"},
            {"label": "Solde apres versement bancaire", "amount": balance_after_bank_transfer, "tone": "violet"},
            {"label": "Remises coupons accordees", "amount": coupon_discount_total, "tone": "violet"},
        ],
    }


def render_manager_financial_report_pdf(*, branch, request):
    report = build_manager_financial_report_context(branch=branch, request=request)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ESFEReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1D4F79"),
    )
    section_style = ParagraphStyle(
        "ESFEReportSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#1D4F79"),
    )
    body_style = ParagraphStyle(
        "ESFEReportBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
    )

    story = [
        Paragraph(f"Situation financiere mensuelle - {branch.name}", title_style),
        Spacer(1, 6),
        Paragraph(
            f"Periode : {report['report_period']['label']} ({report['report_period']['start']} - {report['report_period']['end']})",
            body_style,
        ),
        Paragraph(f"Annexe : {report['report_branch_label']}", body_style),
        Paragraph(
            f"Filtres : type={report['report_cash_type'] or 'tous'} / source={report['report_cash_source'] or 'toutes'}",
            body_style,
        ),
        Spacer(1, 6),
    ]

    summary_table = [["Indicateur", "Montant"]]
    for row in report["report_summary_rows"]:
        summary_table.append([row["label"], _money(row["amount"])])
    summary = Table(summary_table, colWidths=[95 * mm, 70 * mm])
    summary.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1D4F79")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D6DFEA")),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#F8FAFC"), colors.white]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(Paragraph("Synthese", section_style))
    story.append(summary)
    story.append(Spacer(1, 8))

    def _build_source_table(rows, title):
        table_data = [["Source", "Nb", "Montant"]]
        for row in rows:
            if row["amount"] <= 0:
                continue
            table_data.append([row["label"], str(row["count"]), _money(row["amount"])])
        if len(table_data) == 1:
            table_data.append(["Aucune ligne", "0", _money(0)])
        table = Table(table_data, colWidths=[90 * mm, 20 * mm, 55 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF2FB")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1D4F79")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D6DFEA")),
            ("FONTSIZE", (0, 0), (-1, -1), 8.3),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return Paragraph(title, section_style), table

    receipt_title, receipt_table = _build_source_table(report["report_receipt_rows"], "Recettes")
    expense_title, expense_table = _build_source_table(report["report_expense_rows"], "Depenses")
    story.extend([receipt_title, receipt_table, Spacer(1, 6), expense_title, expense_table, Spacer(1, 8)])

    source_rows_table = [["Source comptable", "Entrees", "Sorties", "Net"]]
    for row in report["report_source_rows"]:
        net = (row["in_total"] or 0) - (row["out_total"] or 0)
        if row["in_total"] or row["out_total"]:
            source_rows_table.append([row["label"], _money(row["in_total"]), _money(row["out_total"]), _money(net)])
    source_table = Table(source_rows_table, colWidths=[70 * mm, 35 * mm, 35 * mm, 40 * mm])
    source_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1D4F79")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D6DFEA")),
        ("FONTSIZE", (0, 0), (-1, -1), 8.2),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    story.append(Paragraph("Regroupement par source", section_style))
    story.append(source_table)
    story.append(Spacer(1, 8))

    if report["report_alerts"]:
        alert_rows = [["Alerte", "Message"]]
        for alert in report["report_alerts"]:
            alert_rows.append([alert["title"], alert["message"]])
        alert_table = Table(alert_rows, colWidths=[50 * mm, 100 * mm])
        alert_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#991B1B")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#F5C2C7")),
            ("FONTSIZE", (0, 0), (-1, -1), 8.2),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#FEF2F2"), colors.white]),
        ]))
        story.append(Paragraph("Alertes", section_style))
        story.append(alert_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
