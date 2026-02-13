# inscriptions/services.py

def create_inscription_from_candidature(*, candidature, amount_due):
    """
    Création officielle d’une inscription.
    Le montant est COPIÉ et FIGÉ.
    """

    from inscriptions.models import Inscription

    return Inscription.objects.create(
        candidature=candidature,
        amount_due=amount_due,
        status="created"
    )

