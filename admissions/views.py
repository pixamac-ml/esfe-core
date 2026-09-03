# admissions/views.py

import json
import logging
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.templatetags.static import static

from branches.models import Branch
from formations.models import Programme
from academics.services.academic_years import get_current_academic_year_name
from .forms import CandidatureForm
from .models import CandidatureDocument, Candidature


logger = logging.getLogger(__name__)

TUNNEL_CYCLES = {"licence", "master"}
TUNNEL_DOCUMENT_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"}
TUNNEL_MAX_DOCUMENT_SIZE = 10 * 1024 * 1024


def _programme_cycle_key(programme):
    cycle_slug = (programme.cycle.slug or "").lower()
    cycle_name = (programme.cycle.name or "").lower()
    for cycle_key in TUNNEL_CYCLES:
        if cycle_key in cycle_slug or cycle_key in cycle_name:
            return cycle_key
    return ""


def _build_formation_cards(cycle_slug="all", branch_id=None):
    formations_qs = (
        Programme.objects.accepting_admissions()
        .select_related("cycle", "diploma_awarded")
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
                "cycle": formation.cycle.name,
                "diploma": formation.diploma_awarded.name,
                "duration_years": formation.duration_years,
                "first_year_cost": first_year_cost,
                "short_description": formation.short_description,
                "image_url": formation.illustration.url if formation.illustration else "",
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


def _resolve_branch_token(token):
    token = (token or "").strip()
    if not token:
        return None
    queryset = Branch.objects.filter(is_active=True, accepts_online_registration=True)
    if token.isdigit():
        return queryset.filter(id=int(token)).first()
    return queryset.filter(slug=token).first()


def _initial_tunnel_state(request):
    form_data = _default_form_data()
    cycle_filter = request.GET.get("cycle", "all").strip().lower()
    if cycle_filter not in TUNNEL_CYCLES | {"all"}:
        cycle_filter = "all"

    branch_token = (
        request.GET.get("branch")
        or request.GET.get("annexe")
        or request.GET.get("branch_id")
        or request.GET.get("annexe_id")
    )
    branch = _resolve_branch_token(branch_token)
    if branch:
        form_data.update(
            {
                "branch_id": str(branch.id),
                "branch_name": branch.name,
                "branch_city": branch.city,
                "campus_image": branch.image.url if branch.image else "",
            }
        )

    formation_slug = (
        request.GET.get("formation") or request.GET.get("formation_slug") or ""
    ).strip()
    programme = (
        Programme.objects.accepting_admissions().filter(slug=formation_slug)
        .select_related("cycle")
        .first()
        if formation_slug
        else None
    )
    if programme:
        programme_cycle = _programme_cycle_key(programme)
        form_data.update(
            {
                "formation": programme.title,
                "formation_slug": programme.slug,
                "current_level": programme_cycle,
            }
        )
        if programme_cycle:
            cycle_filter = programme_cycle

    requested_step = request.GET.get("step", "").strip()
    initial_step = int(requested_step) if requested_step in {"1", "2", "3"} else 1
    if initial_step == 1 and (branch or programme):
        initial_step = 3

    if branch and programme:
        step3_phase = "documents"
    elif branch:
        step3_phase = "program"
    else:
        step3_phase = "school"

    has_direct_state = bool(request.GET.keys())
    return form_data, cycle_filter, initial_step, step3_phase, not has_direct_state


def _tunnel_context(
    *,
    form_data,
    cycle_filter,
    branches,
    initial_step,
    initial_step3_phase,
    backend_error="",
    backend_errors=None,
    backend_error_step=1,
    backend_error_field="",
    restore_draft=False,
):
    return {
        "formation_cards": [],
        "selected_cycle": cycle_filter,
        "branches": branches,
        "initial_form_json": json.dumps(form_data),
        "initial_step": initial_step,
        "initial_step3_phase": initial_step3_phase,
        "backend_error": backend_error,
        "backend_errors_json": json.dumps(backend_errors or {}),
        "backend_error_step": backend_error_step,
        "backend_error_field": backend_error_field,
        "restore_draft": restore_draft,
    }


def _first_tunnel_error(errors):
    field_steps = {
        "last_name": 1,
        "first_name": 1,
        "city": 1,
        "email": 2,
        "phone": 2,
        "birth_date": 2,
        "gender": 2,
        "current_level": 2,
        "branch_id": 3,
        "formation_slug": 3,
        "documents": 3,
    }
    for field_name, step_no in field_steps.items():
        if field_name in errors:
            return field_name, step_no, errors[field_name]
    return "", 1, ""


def admission_tunnel(request):
    branches = Branch.objects.filter(is_active=True, accepts_online_registration=True).order_by("name")
    form_data, cycle_filter, initial_step, initial_step3_phase, restore_draft = _initial_tunnel_state(request)
    backend_error = ""
    backend_errors = {}
    backend_error_step = 1
    backend_error_field = ""

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
        restore_draft = False
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
            ("gender", "Veuillez selectionner votre genre.", 2),
            ("current_level", "Veuillez selectionner votre niveau d'etudes.", 2),
            ("branch_id", "Veuillez selectionner un campus.", 3),
            ("formation_slug", "Veuillez selectionner une formation.", 3),
        ]

        for field_name, field_message, _step_no in required_fields:
            if not form_data.get(field_name):
                backend_errors[field_name] = field_message
        if form_data["email"]:
            try:
                validate_email(form_data["email"])
            except ValidationError:
                backend_errors["email"] = "Saisissez une adresse email valide."

        birth_date = parse_date(form_data["birth_date"]) if form_data["birth_date"] else None
        if form_data["birth_date"] and not birth_date:
            backend_errors["birth_date"] = "Saisissez une date de naissance valide."
        elif birth_date and birth_date > timezone.localdate():
            backend_errors["birth_date"] = "La date de naissance ne peut pas etre dans le futur."

        if form_data["gender"] and form_data["gender"] not in {"male", "female"}:
            backend_errors["gender"] = "Veuillez selectionner un genre valide."
        if form_data["current_level"] and form_data["current_level"] not in TUNNEL_CYCLES:
            backend_errors["current_level"] = "Veuillez selectionner un niveau d'etudes valide."
        field_max_lengths = {
            "last_name": 150,
            "first_name": 150,
            "city": 100,
            "email": 254,
            "phone": 30,
            "birth_place": 150,
        }
        for field_name, max_length in field_max_lengths.items():
            if len(form_data[field_name]) > max_length:
                backend_errors[field_name] = "Cette valeur est trop longue."
        if len(form_data["phone"]) > 30:
            backend_errors["phone"] = "Le numero de telephone est trop long."

        programme = None
        if form_data["formation_slug"]:
            programme = (
                Programme.objects.accepting_admissions().filter(slug=form_data["formation_slug"])
                .select_related("cycle")
                .first()
            )
            if not programme:
                backend_errors["formation_slug"] = "La formation selectionnee n'est plus disponible."
            else:
                form_data["formation"] = programme.title
                programme_cycle = _programme_cycle_key(programme)
                if not programme_cycle:
                    backend_errors["formation_slug"] = "Le cycle de cette formation n'est pas pris en charge par le tunnel."
                elif form_data["current_level"] and programme_cycle != form_data["current_level"]:
                    backend_errors["formation_slug"] = "La formation choisie ne correspond pas au niveau selectionne."

        branch = None
        if form_data["branch_id"]:
            if form_data["branch_id"].isdigit():
                branch = Branch.objects.filter(
                    id=int(form_data["branch_id"]),
                    is_active=True,
                    accepts_online_registration=True,
                ).first()
            if not branch:
                backend_errors["branch_id"] = "Le campus selectionne n'est plus disponible."
            else:
                form_data["branch_name"] = branch.name
                form_data["branch_city"] = branch.city
                form_data["campus_image"] = branch.image.url if branch.image else ""

        academic_year_name = ""
        if not backend_errors:
            academic_year_name = get_current_academic_year_name()
            if not academic_year_name:
                backend_errors["formation_slug"] = "Aucune annee academique active n'est configuree."

        if not backend_errors:
            email_in_use = Candidature.objects.filter(
                email__iexact=form_data["email"],
                programme=programme,
                academic_year=academic_year_name,
            ).exists()
            if email_in_use:
                backend_errors["email"] = "Cette adresse email est deja utilisee pour cette formation cette annee."

        uploaded_documents = []
        if not backend_errors:
            programme_documents = programme.required_documents.select_related("document")
            for programme_document in programme_documents:
                file_key = f"document_{programme_document.document.id}"
                uploaded_file = request.FILES.get(file_key)
                if uploaded_file:
                    extension = Path(uploaded_file.name).suffix.lower()
                    if extension not in TUNNEL_DOCUMENT_EXTENSIONS:
                        backend_errors["documents"] = "Un document utilise un format non autorise."
                        break
                    if uploaded_file.size > TUNNEL_MAX_DOCUMENT_SIZE:
                        backend_errors["documents"] = "Chaque document doit peser au maximum 10 Mo."
                        break
                    uploaded_documents.append((programme_document.document, uploaded_file))

        if not backend_errors:
            entry_year = 4 if _programme_cycle_key(programme) == "master" else 1
            try:
                with transaction.atomic():
                    candidature = Candidature.objects.create(
                        programme=programme,
                        branch=branch,
                        academic_year=academic_year_name,
                        entry_year=entry_year,
                        first_name=form_data["first_name"],
                        last_name=form_data["last_name"],
                        birth_date=form_data["birth_date"],
                        birth_place=form_data["birth_place"] or form_data["city"],
                        gender=form_data["gender"],
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
            except Exception:
                logger.exception("Echec de creation d'une candidature depuis le tunnel")
                backend_errors["documents"] = "Une erreur technique est survenue. Reessayez dans un instant."

        if backend_errors:
            backend_error_field, backend_error_step, error_message = _first_tunnel_error(backend_errors)
            backend_error = f"Etape {backend_error_step} : {error_message}"
            initial_step = backend_error_step
            if backend_error_step == 3:
                if backend_error_field == "branch_id":
                    initial_step3_phase = "school"
                elif backend_error_field == "documents":
                    initial_step3_phase = "documents"
                else:
                    initial_step3_phase = "program"

    return render(
        request,
        "admissions/tunnel.html",
        _tunnel_context(
            form_data=form_data,
            cycle_filter=cycle_filter,
            branches=branches,
            initial_step=initial_step,
            initial_step3_phase=initial_step3_phase,
            backend_error=backend_error,
            backend_errors=backend_errors,
            backend_error_step=backend_error_step,
            backend_error_field=backend_error_field,
            restore_draft=restore_draft,
        ),
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
        selected_programme = Programme.objects.accepting_admissions().filter(slug=formation_slug).first()
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
        Programme.objects.accepting_admissions(),
        slug=slug,
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
            current_academic_year_name = get_current_academic_year_name()
            if not current_academic_year_name:
                form.add_error(None, "Aucune annee academique active n'est configuree.")
                messages.error(
                    request,
                    "Impossible d'enregistrer la candidature sans annee academique active configuree."
                )
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
            candidature.academic_year = current_academic_year_name

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
