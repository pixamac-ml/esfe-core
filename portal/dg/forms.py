from datetime import timedelta
import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from accounts.models import Profile
from accounts.position_registry import POSITION_REGISTRY, get_position_definition
from branches.models import Branch
from coupons.models import Coupon
from formations.models import Cycle, Diploma, Filiere, Programme


DG_RECRUITMENT_EXCLUDED_POSITIONS = {
    "student",
    "executive_director",
    "deputy_executive_director",
    "super_admin",
}
DG_RECRUITMENT_POSITION_CHOICES = [
    (code, definition.label)
    for code, definition in POSITION_REGISTRY.items()
    if code not in DG_RECRUITMENT_EXCLUDED_POSITIONS
]


class DgRecruitmentForm(forms.Form):
    # Le registre institutionnel est l'unique nomenclature de rôles. Les
    # fonctions exécutives protégées et le profil étudiant ne sont pas des
    # recrutements RH ordinaires.
    POSITION_CHOICES = DG_RECRUITMENT_POSITION_CHOICES

    first_name = forms.CharField(max_length=80, label="Prénom")
    last_name = forms.CharField(max_length=80, label="Nom")
    personal_email = forms.EmailField(required=False, label="Email personnel")
    professional_email = forms.EmailField(required=False, label="Email professionnel")
    phone = forms.CharField(max_length=30, required=False, label="Téléphone")
    branch = forms.ModelChoiceField(queryset=Branch.objects.filter(is_active=True), required=False, label="Annexe (facultative)")
    position = forms.ChoiceField(choices=POSITION_CHOICES, label="Poste")
    salary_base = forms.IntegerField(min_value=0, required=False, label="Salaire de base")
    teacher_hourly_rate = forms.IntegerField(min_value=0, required=False, label="Tarif horaire enseignant")
    generate_access = forms.BooleanField(required=False, initial=True, label="Activer un accès au portail")
    send_access_email = forms.BooleanField(required=False, initial=True, label="Envoyer le lien sécurisé par email")
    def __init__(self, *args, allowed_branch_ids=None, **kwargs):
        super().__init__(*args, **kwargs)
        branches = Branch.objects.filter(is_active=True)
        if allowed_branch_ids is not None:
            branches = branches.filter(id__in=allowed_branch_ids)
        self.fields["branch"].queryset = branches.order_by("name")

    def clean(self):
        cleaned = super().clean()
        generate_access = bool(cleaned.get("generate_access"))
        send_access_email = bool(cleaned.get("send_access_email"))
        has_email = bool((cleaned.get("professional_email") or cleaned.get("personal_email") or "").strip())
        if generate_access and not has_email:
            self.add_error("professional_email", "Un email est obligatoire pour remettre un accès sécurisé.")
        if generate_access and not send_access_email:
            self.add_error("send_access_email", "La remise d'accès doit passer par le lien sécurisé envoyé par email.")
        if send_access_email and not generate_access:
            self.add_error("send_access_email", "Activez d'abord la génération d'accès ou décochez l'envoi d'email.")
        email = (cleaned.get("professional_email") or cleaned.get("personal_email") or "").strip()
        if email:
            from django.contrib.auth import get_user_model

            if get_user_model().objects.filter(email__iexact=email).exists():
                self.add_error("professional_email", "Un compte utilise déjà cette adresse email.")
        return cleaned

    def profile_position(self):
        position = self.cleaned_data["position"]
        return position

    def profile_role(self):
        # Compatibilite temporaire : la position est la source d'autorite.
        from accounts.services.institutional_access import compatibility_role_for_position

        return compatibility_role_for_position(self.profile_position())


class DgStaffLifecycleForm(forms.Form):
    ACTION_SUSPEND = "suspend"
    ACTION_REACTIVATE = "reactivate"
    ACTION_REVOKE = "revoke"
    ACTION_REASSIGN = "reassign"
    ACTION_UPDATE_ASSIGNMENT = "update_assignment"

    ACTION_CHOICES = [
        (ACTION_SUSPEND, "Suspendre l'accès"),
        (ACTION_REACTIVATE, "Réactiver l'accès"),
        (ACTION_REVOKE, "Révoquer l'accès"),
        (ACTION_REASSIGN, "Changer l'affectation"),
        (ACTION_UPDATE_ASSIGNMENT, "Modifier le rôle et l'affectation"),
    ]

    profile_id = forms.IntegerField(min_value=1)
    action = forms.ChoiceField(choices=ACTION_CHOICES)
    reason = forms.CharField(max_length=500, required=False, label="Motif de la décision", widget=forms.Textarea)
    branch = forms.ModelChoiceField(queryset=Branch.objects.none(), required=False, label="Annexe")
    position = forms.ChoiceField(choices=DgRecruitmentForm.POSITION_CHOICES, required=False, label="Rôle institutionnel")

    def __init__(self, *args, allowed_branch_ids=None, **kwargs):
        super().__init__(*args, **kwargs)
        branches = Branch.objects.filter(is_active=True)
        if allowed_branch_ids is not None:
            branches = branches.filter(id__in=allowed_branch_ids)
        self.fields["branch"].queryset = branches.order_by("name")

    def clean(self):
        cleaned = super().clean()
        action = cleaned.get("action")
        reason = (cleaned.get("reason") or "").strip()
        if action in {
            self.ACTION_SUSPEND,
            self.ACTION_REVOKE,
            self.ACTION_REASSIGN,
            self.ACTION_UPDATE_ASSIGNMENT,
        } and not reason:
            self.add_error("reason", "Un motif est obligatoire pour cette décision DG.")
        if action == self.ACTION_REASSIGN and not cleaned.get("branch"):
            self.add_error("branch", "Sélectionnez l'annexe de destination.")
        if action == self.ACTION_UPDATE_ASSIGNMENT and not cleaned.get("position"):
            self.add_error("position", "Sélectionnez un rôle institutionnel.")
        cleaned["reason"] = reason
        return cleaned


class DgBranchForm(forms.ModelForm):
    """Thin DG adapter over the authoritative Branch model."""

    class Meta:
        model = Branch
        fields = [
            "name",
            "code",
            "slug",
            "address",
            "city",
            "phone",
            "email",
            "manager",
            "is_active",
            "accepts_online_registration",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["manager"].queryset = (
            Profile.objects.filter(
                user__is_active=True,
                user_type="staff",
                position__in={"annex_manager", "branch_manager"},
            )
            .select_related("user")
            .order_by("user__first_name", "user__last_name", "user__username")
            .values_list("user_id", flat=True)
        )
        from django.contrib.auth import get_user_model

        self.fields["manager"].queryset = get_user_model().objects.filter(
            id__in=self.fields["manager"].queryset
        ).order_by("first_name", "last_name", "username")

    def clean_code(self):
        return (self.cleaned_data.get("code") or "").strip().upper()


class DgProgrammeForm(forms.ModelForm):
    """Adaptateur DG sur le catalogue institutionnel existant."""

    class Meta:
        model = Programme
        fields = [
            "title", "filiere", "cycle", "diploma_awarded", "duration_years",
            "short_description", "description", "is_active", "is_public",
            "admissions_open",
        ]
        labels = {
            "title": "Intitulé de la formation",
            "filiere": "Filière",
            "cycle": "Cycle",
            "diploma_awarded": "Diplôme délivré",
            "duration_years": "Durée de la formation",
            "short_description": "Présentation courte",
            "description": "Description détaillée",
            "is_active": "Formation active",
            "is_public": "Visible sur le site public",
            "admissions_open": "Admissions ouvertes",
        }
        help_texts = {
            "duration_years": "Indiquez la durée en années, par exemple 3 ans.",
            "short_description": "Texte court affiché dans les listes et aperçus.",
            "description": "Présentez le contenu et les objectifs de la formation.",
        }
        widgets = {
            "duration_years": forms.NumberInput(attrs={"min": 1, "inputmode": "numeric", "placeholder": "Ex. 3"}),
            "description": forms.Textarea(attrs={"rows": 6}),
        }

    IDENTITY_FIELDS = {
        "title", "filiere", "cycle", "diploma_awarded", "duration_years",
        "short_description", "description",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["filiere"].queryset = Filiere.objects.filter(is_active=True).order_by("name")
        self.fields["cycle"].queryset = Cycle.objects.filter(is_active=True).order_by("min_duration_years", "name")
        self.fields["diploma_awarded"].queryset = Diploma.objects.order_by("name")

    def clean(self):
        cleaned = super().clean()
        cycle = cleaned.get("cycle")
        duration = cleaned.get("duration_years")
        if cycle and duration and not cycle.min_duration_years <= duration <= cycle.max_duration_years:
            self.add_error(
                "duration_years",
                f"La durée doit être comprise entre {cycle.min_duration_years} et {cycle.max_duration_years} ans pour ce cycle.",
            )
        if cleaned.get("admissions_open") and (not cleaned.get("is_active") or not cleaned.get("is_public")):
            self.add_error("admissions_open", "Les admissions exigent une formation active et publiée.")
        if not self.instance.pk and all(cleaned.get(name) for name in ("title", "filiere", "cycle", "diploma_awarded")):
            duplicate = Programme.objects.filter(
                title__iexact=cleaned["title"].strip(),
                filiere=cleaned["filiere"],
                cycle=cleaned["cycle"],
                diploma_awarded=cleaned["diploma_awarded"],
            ).exists()
            if duplicate:
                self.add_error("title", "Cette formation existe déjà pour cette filière, ce cycle et ce diplôme.")
        return cleaned


class _DgReferenceBaseForm(forms.ModelForm):
    """Petite administration DG des référentiels déjà détenus par formations."""

    def clean_name(self):
        name = " ".join((self.cleaned_data.get("name") or "").split())
        model_class = self._meta.model
        duplicate = model_class.objects.filter(name__iexact=name)
        if self.instance.pk:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise ValidationError("Ce référentiel existe déjà.")
        return name


class DgFiliereForm(_DgReferenceBaseForm):
    class Meta:
        model = Filiere
        fields = ["name", "description", "is_active"]
        labels = {
            "name": "Nom de la filière",
            "description": "Description",
            "is_active": "Filière active",
        }
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class DgCycleForm(_DgReferenceBaseForm):
    class Meta:
        model = Cycle
        fields = ["name", "min_duration_years", "max_duration_years", "description", "is_active"]
        labels = {
            "name": "Nom du cycle",
            "min_duration_years": "Durée minimale (années)",
            "max_duration_years": "Durée maximale (années)",
            "description": "Description",
            "is_active": "Cycle actif",
        }
        widgets = {
            "min_duration_years": forms.NumberInput(attrs={"min": 1}),
            "max_duration_years": forms.NumberInput(attrs={"min": 1}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        cleaned = super().clean()
        minimum = cleaned.get("min_duration_years")
        maximum = cleaned.get("max_duration_years")
        if minimum and maximum and minimum > maximum:
            self.add_error("max_duration_years", "La durée maximale doit être supérieure ou égale à la durée minimale.")
        return cleaned


class DgDiplomaForm(_DgReferenceBaseForm):
    class Meta:
        model = Diploma
        fields = ["name", "level"]
        labels = {"name": "Intitulé du diplôme", "level": "Niveau d'enseignement"}


class DgCouponForm(forms.Form):
    INPUT_CLASS = "h-ui-control w-full rounded-ui-input border border-ui-border bg-ui-surface px-3 text-sm text-ui-text focus:border-ui-focus focus:ring-ui-focus"
    DATETIME_FORMAT = "%Y-%m-%dT%H:%M"

    code = forms.CharField(
        max_length=32,
        widget=forms.TextInput(attrs={
            "class": f"{INPUT_CLASS} uppercase",
            "placeholder": "Ex: MASTER-DG-2026",
            "autocomplete": "off",
        }),
    )
    label = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Description interne"}),
    )
    discount_type = forms.ChoiceField(
        choices=Coupon.DISCOUNT_TYPE_CHOICES,
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    value = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS}),
    )
    branches = forms.ModelMultipleChoiceField(
        queryset=Branch.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": INPUT_CLASS, "id": "dg-coupon-branches"}),
        label="Annexes (vide = toutes les annexes)",
    )
    programmes = forms.ModelMultipleChoiceField(
        queryset=Programme.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": INPUT_CLASS, "id": "dg-coupon-programmes"}),
        label="Formations (vide = toutes les formations)",
    )
    valid_from = forms.DateTimeField(
        required=False,
        input_formats=[DATETIME_FORMAT],
        widget=forms.DateTimeInput(
            format=DATETIME_FORMAT,
            attrs={"class": INPUT_CLASS, "type": "datetime-local"},
        ),
    )
    valid_until = forms.DateTimeField(
        input_formats=[DATETIME_FORMAT],
        widget=forms.DateTimeInput(
            format=DATETIME_FORMAT,
            attrs={"class": INPUT_CLASS, "type": "datetime-local"},
        ),
    )
    max_redemptions = forms.IntegerField(
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS}),
    )

    def __init__(self, *args, allowed_branch_ids=None, **kwargs):
        super().__init__(*args, **kwargs)
        branches = Branch.objects.filter(is_active=True)
        if allowed_branch_ids is not None:
            branches = branches.filter(id__in=allowed_branch_ids)
        self.fields["branches"].queryset = branches.order_by("name")
        self.fields["valid_from"].initial = timezone.now()

        selected_branch_ids = []
        if self.is_bound:
            if hasattr(self.data, "getlist"):
                selected_branch_ids = self.data.getlist("branches")
            else:
                selected_branch_ids = self.data.get("branches") or []
        self.fields["programmes"].queryset = self.programmes_queryset_for_branches(selected_branch_ids)

    @staticmethod
    def programmes_queryset_for_branches(branch_ids):
        from academics.models import AcademicClass

        branch_ids = [value for value in (branch_ids or []) if str(value).strip()]
        if not branch_ids:
            return Programme.objects.all().order_by("title")
        programme_ids = (
            AcademicClass.objects.filter(branch_id__in=branch_ids, is_active=True)
            .values_list("programme_id", flat=True)
            .distinct()
        )
        return Programme.objects.filter(id__in=programme_ids).order_by("title")

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()
        if not re.fullmatch(r"[A-Z0-9_-]+", code):
            raise ValidationError(
                "Utilisez uniquement des lettres, chiffres, tirets et underscores, sans espace."
            )
        return code

    def clean(self):
        cleaned = super().clean()
        discount_type = cleaned.get("discount_type")
        value = cleaned.get("value")
        if discount_type == Coupon.DISCOUNT_PERCENTAGE and value is not None and value > 100:
            self.add_error("value", "Un pourcentage doit être compris entre 1 et 100.")

        valid_from = cleaned.get("valid_from") or timezone.now()
        valid_until = cleaned.get("valid_until")
        self.long_validity_warning = bool(
            valid_until and valid_until - valid_from > timedelta(days=30)
        )
        if valid_until and valid_from and valid_until <= valid_from:
            raise ValidationError({"valid_until": "La date de fin doit être postérieure à la date de début."})
        return cleaned
