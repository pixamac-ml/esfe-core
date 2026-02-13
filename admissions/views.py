from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages

from formations.models import Programme
from .forms import CandidatureForm
from .models import CandidatureDocument, Candidature


def apply_to_programme(request, slug):
    """
    Vue publique de candidature :
    - formation préchargée
    - formulaire candidat
    - dépôt des documents requis
    """

    programme = get_object_or_404(
        Programme,
        slug=slug,
        is_active=True
    )

    # Documents requis pour ce programme
    required_documents = programme.required_documents.select_related("document")

    if request.method == "POST":
        # IMPORTANT : request.FILES pour les pièces jointes
        form = CandidatureForm(request.POST)

        if form.is_valid():
            candidature = form.save(commit=False)
            candidature.programme = programme
            candidature.save()

            # ==============================
            # TRAITEMENT DES DOCUMENTS
            # ==============================
            for prd in required_documents:
                uploaded_file = request.FILES.get(
                    f"document_{prd.document.id}"
                )

                if uploaded_file:
                    CandidatureDocument.objects.create(
                        candidature=candidature,
                        document_type=prd.document,
                        file=uploaded_file
                    )

            messages.success(
                request,
                "Votre candidature a été envoyée avec succès. "
                "Elle sera analysée par l’administration."
            )

            # Redirection vers la page de confirmation
            return redirect(
                "admissions:confirmation",
                candidature_id=candidature.id
            )

        else:
            messages.error(
                request,
                "Veuillez corriger les erreurs du formulaire."
            )

    else:
        form = CandidatureForm()

    context = {
        "programme": programme,
        "form": form,
        "required_documents": required_documents,
    }

    return render(
        request,
        "admissions/apply.html",
        context
    )

def candidature_confirmation(request, candidature_id):
    candidature = get_object_or_404(Candidature, id=candidature_id)

    return render(
        request,
        "admissions/confirmation.html",
        {"candidature": candidature}
    )
