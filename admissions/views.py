# admissions/views.py

import json

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.templatetags.static import static

from branches.models import Branch
from formations.models import Programme
from .forms import CandidatureForm
from .models import CandidatureDocument, Candidature


def _build_formation_cards(cycle_slug="all", branch_id=None):
    formations_qs = (
        Programme.objects.filter(is_active=True)
        .select_related("cycle")
        .prefetch_related("years__fees")
        .order_by("title")
    )
    if cycle_slug in {"licence", "master"}:
        formations_qs = formations_qs.filter(cycle__slug__iexact=cycle_slug)

    selected_branch = None
    if branch_id:
        selected_branch = (
            Branch.objects.filter(id=branch_id, is_active=True, accepts_online_registration=True)
            .only("id")
            .first()
        )
        if not selected_branch:
            return []

    cards = []
    for formation in formations_qs:
        first_year = next(iter(formation.years.all()), None)
        first_year_cost = 0
        if first_year:
            first_year_cost = sum(fee.amount for fee in first_year.fees.all())

        cards.append(
            {
                "title": formation.title,
                "slug": formation.slug,
                "duration_years": formation.duration_years,
                "first_year_cost": first_year_cost,
                "details_url": formation.get_absolute_url(),
            }
        )

    return cards


def _default_form_data():
    return {
        "last_name": "",
        "first_name": "",
        "city": "",
        "email": "",
        "phone": "",
        "birth_date": "",
        "birth_place": "",
        "gender": "",
        "current_level": "",
        "formation": "",
        "formation_slug": "",
        "branch_id": "",
        "branch_name": "",
        "branch_city": "",
        "campus_image": "",
    }


def admission_tunnel(request):
    cycle_filter = request.GET.get("cycle", "all").lower()
    branches = Branch.objects.filter(is_active=True, accepts_online_registration=True).order_by("name")
    form_data = _default_form_data()
    backend_error = ""
    backend_errors = {}
    backend_error_step = 1
    backend_error_field = ""
    initial_step = 1
    initial_step3_phase = "school"

    if request.method == "POST":
        form_data = {
            "last_name": request.POST.get("last_name", "").strip(),
            "first_name": request.POST.get("first_name", "").strip(),
            "city": request.POST.get("city", "").strip(),
            "email": request.POST.get("email", "").strip(),
            "phone": request.POST.get("phone", "").strip(),
            "birth_date": request.POST.get("birth_date", "").strip(),
            "birth_place": request.POST.get("birth_place", "").strip(),
            "gender": request.POST.get("gender", "").strip(),
            "current_level": request.POST.get("current_level", "").strip(),
            "formation": request.POST.get("formation", "").strip(),
            "formation_slug": request.POST.get("formation_slug", "").strip(),
            "branch_id": request.POST.get("branch_id", "").strip(),
            "branch_name": request.POST.get("branch_name", "").strip(),
            "branch_city": request.POST.get("branch_city", "").strip(),
            "campus_image": request.POST.get("campus_image", "").strip(),
        }
        initial_step = 4
        if form_data.get("formation_slug"):
            initial_step3_phase = "documents"
        elif form_data.get("branch_id"):
            initial_step3_phase = "program"

        required_fields = [
            ("last_name", "Le champ nom est obligatoire.", 1),
            ("first_name", "Le champ prenom est obligatoire.", 1),
            ("city", "Veuillez renseigner votre ville d'origine.", 1),
            ("email", "Le champ email est obligatoire.", 2),
            ("phone", "Veuillez renseigner votre numero de telephone.", 2),
            ("birth_date", "Veuillez renseigner votre date de naissance.", 2),
            ("current_level", "Veuillez selectionner votre niveau d'etudes.", 2),
            ("branch_id", "Veuillez selectionner un campus.", 3),
            ("formation_slug", "Veuillez selectionner une formation.", 3),
        ]

        for field_name, field_message, step_no in required_fields:
            if not form_data.get(field_name):
                backend_errors[field_name] = field_message
                if not backend_error:
                    backend_error = f"Etape {step_no} : {field_message}"
                    backend_error_step = step_no
                    backend_error_field = field_name

        if backend_errors:
            initial_step = backend_error_step
            if backend_error_step == 3:
                initial_step3_phase = "school" if backend_error_field == "branch_id" else "program"
        else:
            programme = Programme.objects.filter(is_active=True, slug=form_data["formation_slug"]).first()
            branch = Branch.objects.filter(
                id=form_data["branch_id"],
                is_active=True,
                accepts_online_registration=True,
            ).first()
            if not programme or not branch:
                if not branch:
                    backend_errors["branch_id"] = "Le campus selectionne n'est plus disponible."
                    backend_error = f"Etape 3 : {backend_errors['branch_id']}"
                    backend_error_step = 3
                    backend_error_field = "branch_id"
                    initial_step3_phase = "school"
                if not programme:
                    backend_errors["formation_slug"] = "La formation selectionnee n'est plus disponible."
                    if not backend_error:
                        backend_error = f"Etape 3 : {backend_errors['formation_slug']}"
                        backend_error_step = 3
                        backend_error_field = "formation_slug"
                    initial_step3_phase = "program"
                initial_step = 3
            else:
                academic_year_start = timezone.now().year
                entry_year = 4 if form_data["current_level"].lower() == "master" else 1
                email_in_use = Candidature.objects.filter(
                    email__iexact=form_data["email"],
                    programme=programme,
                    academic_year=f"{academic_year_start}-{academic_year_start + 1}",
                ).exists()
                if email_in_use:
                    backend_errors["email"] = "Cette adresse email est deja utilisee pour cette formation cette annee."
                    backend_error = f"Etape 2 : {backend_errors['email']}"
                    backend_error_step = 2
                    backend_error_field = "email"
                    initial_step = 2
                    initial_step3_phase = "program"
                    formation_cards = []
                    return render(
                        request,
                        "admissions/tunnel.html",
                        {
                            "formation_cards": formation_cards,
                            "selected_cycle": cycle_filter,
                            "branches": branches,
                            "initial_form_json": json.dumps(form_data),
                            "initial_step": initial_step,
                            "initial_step3_phase": initial_step3_phase,
                            "backend_error": backend_error,
                            "backend_errors_json": json.dumps(backend_errors),
                            "backend_error_step": backend_error_step,
                            "backend_error_field": backend_error_field,
                        },
                    )

                programme_documents = programme.required_documents.select_related("document")
                uploaded_documents = []

                for programme_document in programme_documents:
                    file_key = f"document_{programme_document.document.id}"
                    uploaded_file = request.FILES.get(file_key)
                    if uploaded_file:
                        uploaded_documents.append((programme_document.document, uploaded_file))

                try:
                    with transaction.atomic():
                        candidature = Candidature.objects.create(
                            programme=programme,
                            branch=branch,
                            academic_year=f"{academic_year_start}-{academic_year_start + 1}",
                            entry_year=entry_year,
                            first_name=form_data["first_name"],
                            last_name=form_data["last_name"],
                            birth_date=form_data["birth_date"],
                            birth_place=form_data["birth_place"] or form_data["city"],
                            gender=form_data["gender"] if form_data["gender"] in {"male", "female"} else "male",
                            phone=form_data["phone"],
                            email=form_data["email"],
                            city=form_data["city"],
                            country="Mali",
                        )

                        for document_type, uploaded_file in uploaded_documents:
                            CandidatureDocument.objects.create(
                                candidature=candidature,
                                document_type=document_type,
                                file=uploaded_file,
                            )

                    messages.success(request, "Votre candidature a ete enregistree avec succes.")
                    return redirect("admissions:done", candidature_id=candidature.id)
                except IntegrityError:
                    backend_errors["email"] = "Cette adresse email est deja utilisee pour cette formation cette annee."
                    backend_error = f"Etape 2 : {backend_errors['email']}"
                    backend_error_step = 2
                    backend_error_field = "email"
                    initial_step = 2
                    initial_step3_phase = "program"
                except Exception:
                    backend_error = "Une erreur technique est survenue. Reessayez dans un instant."
                    initial_step = 3
                    initial_step3_phase = "documents"

    formation_cards = []
    return render(
        request,
        "admissions/tunnel.html",
        {
            "formation_cards": formation_cards,
            "selected_cycle": cycle_filter,
            "branches": branches,
            "initial_form_json": json.dumps(form_data),
            "initial_step": initial_step,
            "initial_step3_phase": initial_step3_phase,
            "backend_error": backend_error,
            "backend_errors_json": json.dumps(backend_errors),
            "backend_error_step": backend_error_step,
            "backend_error_field": backend_error_field,
        },
    )


def admission_step3_formations(request):
    cycle_filter = request.GET.get("cycle", "").strip().lower()
    if not cycle_filter:
        cycle_filter = request.GET.get("current_level", "all").strip().lower()
    if cycle_filter not in {"all", "licence", "master"}:
        cycle_filter = "all"
    branch_id_raw = request.GET.get("branch_id", "").strip() or request.GET.get("annexe_id", "").strip()
    branch_id = None
    if branch_id_raw.isdigit():
        branch_id = int(branch_id_raw)

    selected_branch = None
    if branch_id:
        selected_branch = Branch.objects.filter(
            id=branch_id,
            is_active=True,
            accepts_online_registration=True,
        ).first()

    formation_cards = _build_formation_cards(cycle_filter, branch_id=branch_id)
    return render(
        request,
        "admissions/partials/formation_options.html",
        {
            "formation_cards": formation_cards,
            "selected_cycle": cycle_filter,
            "selected_branch": selected_branch,
        },
    )


def admission_step3_documents(request):
    formation_slug = request.GET.get("formation_slug", "").strip()
    selected_programme = None
    required_documents = []

    if formation_slug:
        selected_programme = Programme.objects.filter(
            slug=formation_slug,
            is_active=True,
        ).first()
        if selected_programme:
            required_documents = selected_programme.required_documents.select_related("document")

    return render(
        request,
        "admissions/partials/step3_documents.html",
        {
            "selected_programme": selected_programme,
            "required_documents": required_documents,
        },
    )


def admission_done(request, candidature_id):
    candidature = get_object_or_404(Candidature.objects.select_related("programme"), id=candidature_id)
    return render(request, "admissions/done.html", {"candidature": candidature})


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