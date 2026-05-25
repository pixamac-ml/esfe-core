from django.db.models import Sum

from payments.models import Payment


def get_finance_widget(user):
    student = getattr(user, "student_profile", None)
    if student is None:
        return {
            "total_due": "Non disponible",
            "total_paid": "Non disponible",
            "remaining": "Non disponible",
            "status": "En attente",
            "status_tone": "warning",
            "metrics": [
                {"label": "Total a payer", "value": "Non disponible", "icon": "receipt"},
                {"label": "Total paye", "value": "Non disponible", "icon": "check-circle-2"},
                {"label": "Reste a regler", "value": "Non disponible", "icon": "wallet"},
            ],
            "payments": [],
        }

    inscription = student.inscription
    total_due = inscription.amount_due or 0
    total_paid = (
        Payment.objects.filter(
            inscription=inscription,
            status=Payment.STATUS_VALIDATED,
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )
    remaining = max(total_due - total_paid, 0)

    return {
        "total_due": total_due,
        "total_paid": total_paid,
        "remaining": remaining,
        "status": inscription.get_status_display(),
        "status_tone": "success" if remaining == 0 else "warning",
        "metrics": [
            {"label": "Total a payer", "value": total_due, "icon": "receipt"},
            {"label": "Total paye", "value": total_paid, "icon": "check-circle-2"},
            {"label": "Reste a regler", "value": remaining, "icon": "wallet"},
        ],
        "payments": [
            {
                "amount": payment.amount,
                "method": payment.get_method_display(),
                "status": payment.get_status_display(),
                "status_tone": "success" if payment.status == Payment.STATUS_VALIDATED else "warning",
                "date": payment.paid_at,
                "reference": payment.receipt_number or payment.reference or f"Paiement #{payment.id}",
            }
            for payment in Payment.objects.filter(inscription=inscription).order_by("-paid_at")[:6]
        ],
    }
