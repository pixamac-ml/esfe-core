from django import forms

from .models import AcademicCorrectionRequest, TransferRequest


class TransferRequestForm(forms.ModelForm):
    class Meta:
        model = TransferRequest
        fields = ("target_branch", "requested_programme", "requested_class", "requested_branch", "reason")


class AcademicCorrectionRequestForm(forms.ModelForm):
    class Meta:
        model = AcademicCorrectionRequest
        fields = ("student", "academic_year", "branch", "academic_class", "request_type", "description")
