from django import forms
from django.contrib.auth import get_user_model

from shop.models import ShopPayment, ShopProduct, ShopStockMovement
from shop.services.shop_cash_session import validate_shop_cash_session_code, verify_agent_and_create_shop_session
INPUT_CLASS = "w-full rounded-xl border border-slate-200 px-4 py-3 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary"
TEXTAREA_CLASS = "w-full rounded-xl border border-slate-200 px-4 py-3 text-sm min-h-[90px] focus:ring-2 focus:ring-primary/20 focus:border-primary"
CHECKBOX_CLASS = "rounded border-slate-300 text-primary focus:ring-primary"
User = get_user_model()


class ShopProductForm(forms.ModelForm):
    class Meta:
        model = ShopProduct
        fields = ["name", "image", "category", "description", "unit_price", "is_required", "low_stock_threshold", "is_active"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ["name", "category", "unit_price", "low_stock_threshold"]:
            self.fields[name].widget.attrs.update({"class": INPUT_CLASS})
        self.fields["name"].widget.attrs.update({"placeholder": "Ex: Kit de cours L1"})
        self.fields["unit_price"].widget.attrs.update({"placeholder": "Ex: 25000"})
        self.fields["low_stock_threshold"].widget.attrs.update({"placeholder": "Ex: 5"})
        self.fields["image"].widget.attrs.update({
            "class": INPUT_CLASS,
            "accept": "image/*",
        })
        self.fields["description"].widget.attrs.update({
            "class": TEXTAREA_CLASS,
            "placeholder": "Presentation courte de l'article, contenu, usage ou precision utile.",
        })
        for name in ["is_required", "is_active"]:
            self.fields[name].widget.attrs.update({"class": CHECKBOX_CLASS})


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


class StudentShopPaymentForm(forms.Form):
    """Paiement commande boutique côté étudiant — aligné sur le formulaire de scolarité."""

    method = forms.ChoiceField(
        choices=[],
        label="Methode de paiement",
        widget=forms.Select(
            attrs={"class": INPUT_CLASS}
        ),
    )
    agent_name = forms.CharField(
        required=False,
        label="Nom de l'agent",
        widget=forms.TextInput(
            attrs={
                "class": INPUT_CLASS,
                "placeholder": "Ex : Fatoumata Dia",
            }
        ),
    )
    verification_code = forms.CharField(
        required=False,
        label="Code de validation",
        max_length=6,
        widget=forms.TextInput(
            attrs={
                "class": f"{INPUT_CLASS} font-mono text-center tracking-widest text-lg max-w-[12rem]",
                "placeholder": "------",
                "maxlength": "6",
            }
        ),
    )
    amount = forms.IntegerField(
        min_value=1,
        label="Montant a payer (FCFA)",
        widget=forms.NumberInput(
            attrs={
                "class": INPUT_CLASS,
                "placeholder": "Ex : 50000",
                "min": "1",
            }
        ),
    )

    def __init__(self, *args, order=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["method"].choices = ShopPayment.METHOD_CHOICES
        self.order = order
        self.agent = None
        self.cash_session = None
        balance = getattr(order, "balance", None)
        max_amount = balance if balance is not None else 0
        if max_amount > 0:
            self.fields["amount"].widget.attrs["max"] = str(max_amount)
    def clean(self):
        cleaned = super().clean()
        if not self.order:
            raise forms.ValidationError("Commande invalide.")

        amount = cleaned.get("amount")
        method = cleaned.get("method")
        agent_name = cleaned.get("agent_name")
        code = (cleaned.get("verification_code") or "").strip()

        if amount is None or amount <= 0:
            raise forms.ValidationError("Montant invalide.")

        balance = self.order.balance
        if amount > balance:
            self.add_error("amount", "Le montant depasse le solde restant de la commande.")

        if method == ShopPayment.METHOD_CASH:
            if not agent_name:
                raise forms.ValidationError(
                    "Veuillez entrer le nom de l'agent charge du paiement boutique."
                )
            agent, error = verify_agent_and_create_shop_session(self.order, agent_name)
            if error:
                raise forms.ValidationError(error)
            if not code:
                raise forms.ValidationError(
                    "Veuillez entrer le code de validation communique par l'agent."
                )
            session, error = validate_shop_cash_session_code(self.order, agent, code)
            if error:
                raise forms.ValidationError(error)
            self.agent = agent
            self.cash_session = session

        elif method in {ShopPayment.METHOD_ORANGE, ShopPayment.METHOD_BANK}:
            cleaned["verification_code"] = ""
            cleaned["agent_name"] = ""

        return cleaned


class ShopCounterOrderForm(forms.Form):
    buyer_type = forms.ChoiceField(choices=(
        ("walk_in", "Vente comptoir"),
        ("student", "Etudiant"),
    ))
    student = forms.ModelChoiceField(queryset=User.objects.none(), required=False)
    customer_name = forms.CharField(required=False, max_length=180)
    customer_email = forms.EmailField(required=False)
    customer_phone = forms.CharField(required=False, max_length=40)
    product = forms.ModelChoiceField(queryset=ShopProduct.objects.none())
    quantity = forms.IntegerField(min_value=1, initial=1)
    payment_method = forms.ChoiceField(choices=ShopPayment.METHOD_CHOICES)

    def __init__(self, *args, branch=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = ShopProduct.objects.filter(branch=branch, is_active=True) if branch else ShopProduct.objects.none()
        if branch:
            self.fields["student"].queryset = User.objects.filter(
                student_profile__inscription__candidature__branch=branch,
                student_profile__is_active=True,
            ).select_related("student_profile")
        for field_name in ["buyer_type", "student", "customer_name", "customer_email", "customer_phone", "product", "quantity", "payment_method"]:
            self.fields[field_name].widget.attrs.update({"class": INPUT_CLASS})
        self.fields["customer_name"].widget.attrs.update({"placeholder": "Nom du client"})
        self.fields["customer_email"].widget.attrs.update({"placeholder": "Email du client"})
        self.fields["customer_phone"].widget.attrs.update({"placeholder": "Telephone du client"})

    def clean(self):
        cleaned = super().clean()
        buyer_type = cleaned.get("buyer_type")
        student = cleaned.get("student")
        customer_name = (cleaned.get("customer_name") or "").strip()
        if buyer_type == "student":
            if not student:
                self.add_error("student", "Selectionnez un etudiant.")
        elif not customer_name:
            self.add_error("customer_name", "Le nom du client est requis pour une vente comptoir.")
        return cleaned


class ShopPublicOrderForm(forms.Form):
    buyer_type = forms.ChoiceField(choices=(
        ("student", "Etudiant"),
        ("walk_in", "Acheteur libre"),
    ))
    student_identifier = forms.CharField(required=False, max_length=80)
    customer_first_name = forms.CharField(required=False, max_length=90)
    customer_last_name = forms.CharField(required=False, max_length=90)
    customer_email = forms.EmailField(required=False)
    customer_phone = forms.CharField(required=False, max_length=40)
    quantity = forms.IntegerField(min_value=1, initial=1)
    payment_method = forms.ChoiceField(choices=ShopPayment.METHOD_CHOICES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ["buyer_type", "student_identifier", "customer_first_name", "customer_last_name", "customer_email", "customer_phone", "quantity", "payment_method"]:
            self.fields[field_name].widget.attrs.update({"class": INPUT_CLASS})
        self.fields["student_identifier"].widget.attrs.update({
            "placeholder": "ID utilisateur, username ou matricule etudiant",
        })
        self.fields["customer_first_name"].widget.attrs.update({"placeholder": "Prenom"})
        self.fields["customer_last_name"].widget.attrs.update({"placeholder": "Nom"})
        self.fields["customer_email"].widget.attrs.update({"placeholder": "adresse@email.com"})
        self.fields["customer_phone"].widget.attrs.update({"placeholder": "Telephone"})

    def clean(self):
        cleaned = super().clean()
        buyer_type = cleaned.get("buyer_type")
        student_identifier = (cleaned.get("student_identifier") or "").strip()
        customer_first_name = (cleaned.get("customer_first_name") or "").strip()
        customer_last_name = (cleaned.get("customer_last_name") or "").strip()
        customer_email = (cleaned.get("customer_email") or "").strip()
        if buyer_type == "student":
            if not student_identifier:
                self.add_error("student_identifier", "Renseignez l'identifiant etudiant.")
        else:
            if not customer_first_name:
                self.add_error("customer_first_name", "Le prenom est requis.")
            if not customer_last_name:
                self.add_error("customer_last_name", "Le nom est requis.")
            if not customer_email:
                self.add_error("customer_email", "L'email est requis pour notifier l'acheteur.")
            cleaned["customer_name"] = " ".join(part for part in [customer_first_name, customer_last_name] if part).strip()
        return cleaned
