from django import forms


class ApplyCouponForm(forms.Form):
    code = forms.CharField(
        max_length=32,
        label="Code coupon",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Ex: MASTER-DG-2026",
                "class": "form-control text-uppercase",
                "autocomplete": "off",
            }
        ),
    )
