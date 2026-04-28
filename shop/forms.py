from django import forms

from shop.models import ShopPayment, ShopProduct, ShopStockMovement


INPUT_CLASS = "w-full rounded-xl border border-slate-200 px-4 py-3 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary"
TEXTAREA_CLASS = "w-full rounded-xl border border-slate-200 px-4 py-3 text-sm min-h-[90px] focus:ring-2 focus:ring-primary/20 focus:border-primary"


class ShopProductForm(forms.ModelForm):
    class Meta:
        model = ShopProduct
        fields = ["name", "category", "description", "unit_price", "is_required", "low_stock_threshold", "is_active"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ["name", "category", "unit_price", "low_stock_threshold"]:
            self.fields[name].widget.attrs.update({"class": INPUT_CLASS})
        self.fields["description"].widget.attrs.update({"class": TEXTAREA_CLASS})
        for name in ["is_required", "is_active"]:
            self.fields[name].widget.attrs.update({"class": "rounded border-slate-300 text-primary focus:ring-primary"})


class ShopStockInForm(forms.Form):
    product = forms.ModelChoiceField(queryset=ShopProduct.objects.none())
    quantity = forms.IntegerField(min_value=1)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, branch=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = ShopProduct.objects.filter(branch=branch, is_active=True) if branch else ShopProduct.objects.none()
        self.fields["product"].widget.attrs.update({"class": INPUT_CLASS})
        self.fields["quantity"].widget.attrs.update({"class": INPUT_CLASS})
        self.fields["notes"].widget.attrs.update({"class": TEXTAREA_CLASS})


class ShopPaymentForm(forms.Form):
    method = forms.ChoiceField(choices=ShopPayment.METHOD_CHOICES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["method"].widget.attrs.update({"class": INPUT_CLASS})
