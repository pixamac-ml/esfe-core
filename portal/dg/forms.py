from django import forms

from accounts.models import Profile
from branches.models import Branch


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
