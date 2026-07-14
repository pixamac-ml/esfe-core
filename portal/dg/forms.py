from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from accounts.models import Profile
from branches.models import Branch
from coupons.models import Coupon
from formations.models import Programme


class DgRecruitmentForm(forms.Form):
    POSITION_CHOICES = [
        ("branch_manager", "Gestionnaire annexe"),
        ("academic_supervisor", "Surveillant academique"),
        ("it_support", "Informaticien"),
        ("finance_manager", "Responsable finance"),
        ("admissions", "Admissions"),
        ("secretary", "Secretaire"),
        ("other", "Autre poste"),
    ]

    first_name = forms.CharField(max_length=80)
    last_name = forms.CharField(max_length=80)
    personal_email = forms.EmailField(required=False)
    professional_email = forms.EmailField(required=False)
    phone = forms.CharField(max_length=30, required=False)
    branch = forms.ModelChoiceField(queryset=Branch.objects.filter(is_active=True), required=False)
    position = forms.ChoiceField(choices=POSITION_CHOICES)
    salary_base = forms.IntegerField(min_value=0, required=False)
    generate_access = forms.BooleanField(required=False, initial=True)
    send_access_email = forms.BooleanField(required=False, initial=True)
    business_description = forms.CharField(required=False, widget=forms.Textarea)
    responsibilities = forms.CharField(required=False, widget=forms.Textarea)
    expected_dashboard = forms.CharField(required=False, widget=forms.Textarea)
    required_permissions = forms.CharField(required=False, widget=forms.Textarea)
    concerned_branches = forms.CharField(required=False, widget=forms.Textarea)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["branch"].queryset = Branch.objects.filter(is_active=True).order_by("name")
        self.fields["branch"].widget.attrs.update(
            {"class": "mt-1 h-12 w-full rounded-xl border border-slate-200 px-3 text-sm font-bold"}
        )

    def clean(self):
        cleaned = super().clean()
        position = cleaned.get("position")
        if position == "other":
            required = [
                "business_description",
                "responsibilities",
                "expected_dashboard",
                "required_permissions",
                "concerned_branches",
            ]
            for field in required:
                if not (cleaned.get(field) or "").strip():
                    self.add_error(field, "Champ obligatoire pour un autre poste.")
        return cleaned

    def profile_position(self):
        position = self.cleaned_data["position"]
        if position == "other":
            return ""
        return position

    def profile_role(self):
        position = self.cleaned_data["position"]
        if position == "finance_manager":
            return "finance"
        if position == "admissions":
            return "admissions"
        if position in {"branch_manager", "academic_supervisor", "it_support", "secretary"}:
            return ""
        return ""


class DgCouponForm(forms.Form):
    INPUT_CLASS = "mt-1 h-12 w-full rounded-xl border border-slate-200 px-3 text-sm font-bold"

    code = forms.CharField(
        max_length=32,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Ex: MASTER-DG-2026"}),
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
        widget=forms.DateTimeInput(attrs={"class": INPUT_CLASS, "type": "datetime-local"}),
    )
    valid_until = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={"class": INPUT_CLASS, "type": "datetime-local"}),
    )
    max_redemptions = forms.IntegerField(
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["branches"].queryset = Branch.objects.filter(is_active=True).order_by("name")
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

    def clean(self):
        cleaned = super().clean()
        valid_from = cleaned.get("valid_from") or timezone.now()
        valid_until = cleaned.get("valid_until")
        self.long_validity_warning = bool(
            valid_until and valid_until - valid_from > timedelta(days=30)
        )
        if valid_until and valid_from and valid_until <= valid_from:
            raise ValidationError({"valid_until": "La date de fin doit être postérieure à la date de début."})
        return cleaned
