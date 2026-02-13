from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import cm


def build_receipt_pdf(response, receipt):
    payment = receipt.payment
    inscription = payment.inscription
    candidature = inscription.candidature
    programme = candidature.programme

    doc = SimpleDocTemplate(
        response,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    elements = []

    # ==========================
    # EN-TÊTE
    # ==========================
    elements.append(
        Paragraph(
            "<b>ÉCOLE SUPÉRIEURE DE FORMATION ESFE</b><br/>"
            "Reçu officiel de paiement",
            styles["Title"],
        )
    )

    elements.append(Spacer(1, 20))

    # ==========================
    # INFOS REÇU
    # ==========================
    elements.append(
        Paragraph(
            f"<b>Référence du reçu :</b> {receipt.reference}<br/>"
            f"<b>Date :</b> {receipt.issued_at.strftime('%d/%m/%Y %H:%M')}",
            styles["Normal"],
        )
    )

    elements.append(Spacer(1, 20))

    # ==========================
    # TABLE INFOS
    # ==========================
    table_data = [
        ["Candidat", f"{candidature.last_name} {candidature.first_name}"],
        ["Email", candidature.email],
        ["Téléphone", candidature.phone],
        ["Formation", programme.title],
        ["Cycle", programme.cycle.name],
        ["Montant payé", f"{payment.amount} FCFA"],
        ["Méthode de paiement", payment.get_method_display()],
        ["Statut", payment.get_status_display()],
    ]

    table = Table(table_data, colWidths=[6 * cm, 8 * cm])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    elements.append(table)
    elements.append(Spacer(1, 30))

    # ==========================
    # SIGNATURE
    # ==========================
    elements.append(
        Paragraph(
            "Ce reçu atteste que le paiement ci-dessus a été enregistré "
            "par l’administration de l’ESFE.",
            styles["Normal"],
        )
    )

    elements.append(Spacer(1, 40))

    elements.append(
        Paragraph(
            "<b>Administration ESFE</b><br/>"
            "Signature et cachet",
            styles["Normal"],
        )
    )

    doc.build(elements)
