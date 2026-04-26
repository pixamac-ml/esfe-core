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
    }
