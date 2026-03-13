# admissions/views.py

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from django.templatetags.static import static

from formations.models import Programme
from .forms import CandidatureForm
from .models import CandidatureDocument, Candidature


def apply_to_programme(request, slug):
    """
    Vue publique de candidature :
    - formation préchargée
    - formulaire candidat avec choix d'annexe
    - dépôt des documents requis
    - prévention des doublons d'email
    """

    programme = get_object_or_404(
        Programme,
        slug=slug,
        is_active=True
    )

    # Documents requis pour ce programme
    required_documents = programme.required_documents.select_related("document")

    if request.method == "POST":

        form = CandidatureForm(request.POST)

        if form.is_valid():

            # On prépare la candidature sans sauvegarder
            candidature = form.save(commit=False)
            candidature.programme = programme

            # année académique actuelle
            current_year = timezone.now().year
            candidature.academic_year = f"{current_year}-{current_year + 1}"

            # ==============================
            # VERIFICATION EMAIL EXISTANT
            # ==============================

            email = candidature.email

            existing = Candidature.objects.filter(
                email=email,
                programme=programme,
                academic_year=candidature.academic_year
            ).exists()

            if existing:

                form.add_error(
                    "email",
                    "Une candidature existe déjà avec cette adresse email pour ce programme cette année."
                )

                messages.warning(
                    request,
                    "Une candidature avec cette adresse email existe déjà."
                )

            else:

                # ==============================
                # ENREGISTREMENT CANDIDATURE
                # ==============================

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
                    f"Votre candidature à l'annexe {candidature.branch.name} a été envoyée avec succès."
                )

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
        "lab_image": static("images/lab_students.png"),
    }

    return render(
        request,
        "admissions/apply.html",
        context
    )


def candidature_confirmation(request, candidature_id):

    candidature = get_object_or_404(
        Candidature.objects.select_related("programme", "branch"),
        id=candidature_id
    )

    return render(
        request,
        "admissions/confirmation.html",
        {"candidature": candidature}
    )