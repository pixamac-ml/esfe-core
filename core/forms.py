from django import forms
from .models import ContactMessage


class ContactForm(forms.ModelForm):

    consent = forms.BooleanField(
        required=True,
        label="J’accepte que mes données soient utilisées pour traiter ma demande."
    )

    class Meta:
        model = ContactMessage
        fields = [
            "full_name",
            "email",
            "phone",
            "subject",
            "message",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        base_input_class = (
            "w-full rounded-xl border border-slate-300 px-4 py-2 "
            "focus:ring-2 focus:ring-slate-800 focus:outline-none "
            "transition duration-200"
        )

        # Champs texte
        for name, field in self.fields.items():
            if name not in ["consent"]:
                field.widget.attrs.update({
                    "class": base_input_class
                })

        # Select styling spécifique
        self.fields["subject"].widget.attrs.update({
            "class": base_input_class + " bg-white"
        })

        # Textarea
        self.fields["message"].widget.attrs.update({
            "rows": 4,
            "placeholder": "Décrivez votre demande avec précision..."
        })

        # Placeholders
        self.fields["full_name"].widget.attrs.update({
            "placeholder": "Votre nom complet"
        })

        self.fields["email"].widget.attrs.update({
            "placeholder": "exemple@email.com"
        })

        self.fields["phone"].widget.attrs.update({
            "placeholder": "Numéro de téléphone"
        })

        # Checkbox
        self.fields["consent"].widget.attrs.update({
            "class": (
                "h-4 w-4 rounded border-slate-300 "
                "text-slate-800 focus:ring-slate-800"
            )
        })