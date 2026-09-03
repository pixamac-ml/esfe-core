from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.core.validators import FileExtensionValidator
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from academics.models import (
    AcademicClass,
    AcademicEnrollment,
    AcademicScheduleEvent,
    AcademicYear,
    EC,
    EvaluationCampaign,
    Semester,
    UE,
    WeeklyScheduleSlot,
)
from branches.models import Branch
from formations.models import Programme
from notifier.models import NotificationMessage
from portal.models import AdministrativeDocument, TeacherDocument, TransferDocument, TransferRequest


INPUT_CLASS = (
    "h-11 w-full max-w-full rounded-ui-input border border-ui-border "
    "bg-ui-surface px-3 text-sm text-ui-text outline-none "
    "focus:border-ui-focus focus:ring-2 focus:ring-ui-focus/20"
)
TEXTAREA_CLASS = (
    "min-h-24 w-full max-w-full resize-y rounded-ui-input border "
    "border-ui-border bg-ui-surface px-3 py-2 text-sm text-ui-text "
    "outline-none focus:border-ui-focus focus:ring-2 focus:ring-ui-focus/20"
)
FILE_INPUT_CLASS = (
    "block w-full rounded-ui-input border border-ui-border bg-ui-surface px-3 py-2 "
    "text-sm text-ui-text file:mr-3 file:rounded-ui-button file:border-0 "
    "file:bg-ui-primary-soft file:px-3 file:py-2 file:text-xs file:font-semibold "
    "file:text-ui-primary focus:border-ui-focus focus:ring-2 focus:ring-ui-focus/20"
)


class AcademicClassChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.display_name


class ECChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.title


class TeacherChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.get_full_name() or obj.username


class EnrollmentChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        student_name = obj.student.get_full_name() or obj.student.username
        return f"{student_name} · {obj.academic_class.display_name}"


class ProgrammeChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.title} · {obj.cycle.name}" if obj.cycle_id else obj.title


class SemesterChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"Semestre {obj.number}"


class UEChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"S{obj.semester.number} · {obj.code} · {obj.title}"


class DirectorTeacherCreateForm(forms.Form):
    last_name = forms.CharField(
        label="Nom",
        max_length=150,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "autocomplete": "family-name"}),
    )
    first_name = forms.CharField(
        label="Prénom",
        max_length=150,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "autocomplete": "given-name"}),
    )
    email = forms.EmailField(
        label="Adresse email",
        widget=forms.EmailInput(
            attrs={"class": INPUT_CLASS, "autocomplete": "email", "placeholder": "prenom.nom@exemple.com"}
        ),
    )
    phone = forms.CharField(
        label="Téléphone",
        max_length=40,
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "autocomplete": "tel", "placeholder": "+223 00 00 00 00"}),
    )
    specialty = forms.CharField(
        label="Spécialité principale",
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Ex. Comptabilité, anglais"}),
    )
    teacher_hourly_rate = forms.IntegerField(
        label="Tarif horaire (FCFA)",
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "500", "placeholder": "Ex. 5000"}),
    )
    class_id = AcademicClassChoiceField(
        label="Classe initiale",
        queryset=AcademicClass.objects.none(),
        required=False,
        empty_label="Aucune affectation initiale",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    ec_id = ECChoiceField(
        label="Matière (EC)",
        queryset=EC.objects.none(),
        required=False,
        empty_label="Toute la classe / aucune matière précise",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
        error_messages={"invalid_choice": "La matiere selectionnee n'appartient pas a la classe choisie."},
    )
    room_label = forms.CharField(
        label="Salle de référence",
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Ex. Salle B12"}),
    )
    planned_hours = forms.DecimalField(
        label="Volume horaire prévu",
        min_value=Decimal("0.50"),
        max_digits=6,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.5", "placeholder": "Ex. 24"}),
        error_messages={"required": "Le volume horaire est obligatoire pour cette affectation."},
    )

    def __init__(self, *args, branch=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.branch = branch
        if branch is None:
            return
        self.fields["class_id"].queryset = AcademicClass.objects.select_related(
            "programme", "academic_year"
        ).filter(branch=branch, is_active=True, is_archived=False).order_by(
            "level", "programme__title", "id"
        )
        self.fields["class_id"].widget.attrs.update(
            {
                "hx-get": f"{reverse('accounts_portal:director_teacher_ec_options')}?mode=create",
                "hx-target": "#director-teacher-create-ec-field",
                "hx-swap": "innerHTML",
                "hx-trigger": "change",
                "hx-indicator": "#director-teacher-form-loading",
            }
        )
        selected_class_id = self.data.get(self.add_prefix("class_id")) if self.is_bound else self.initial.get("class_id")
        if str(getattr(selected_class_id, "pk", selected_class_id) or "").isdigit():
            self.fields["ec_id"].queryset = EC.objects.select_related(
                "ue", "ue__semester"
            ).filter(
                ue__semester__academic_class_id=int(getattr(selected_class_id, "pk", selected_class_id)),
                ue__semester__academic_class__branch=branch,
            ).exclude(structure_status=EC.STRUCTURE_ARCHIVED).order_by(
                "ue__semester__number", "ue__code", "title", "id"
            )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Cette adresse email est déjà utilisée.")
        return email

    def clean(self):
        cleaned = super().clean()
        academic_class = cleaned.get("class_id")
        ec = cleaned.get("ec_id")
        if ec and not academic_class:
            self.add_error("class_id", "Choisissez d'abord la classe de cette matière.")
        if academic_class and ec and ec.ue.semester.academic_class_id != academic_class.id:
            self.add_error("ec_id", "Cette matière n'appartient pas à la classe choisie.")
        if academic_class and not cleaned.get("room_label"):
            self.add_error("room_label", "Indiquez la salle de référence pour cette affectation.")
        if academic_class and cleaned.get("planned_hours") is None:
            self.add_error("planned_hours", "Indiquez le volume horaire prévu.")
        return cleaned


class DirectorTeacherAssignmentForm(forms.Form):
    class_id = AcademicClassChoiceField(
        label="Classe",
        queryset=AcademicClass.objects.none(),
        empty_label="Choisir une classe",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    ec_id = ECChoiceField(
        label="Matière (EC)",
        queryset=EC.objects.none(),
        required=False,
        empty_label="Affectation au niveau de la classe",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
        error_messages={"invalid_choice": "La matiere selectionnee n'appartient pas a la classe choisie."},
    )
    room_label = forms.CharField(
        label="Salle de référence",
        max_length=120,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Ex. Salle B12"}),
    )
    planned_hours = forms.DecimalField(
        label="Volume horaire prévu",
        min_value=Decimal("0.50"),
        max_digits=6,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.5", "placeholder": "Ex. 24"}),
        error_messages={"required": "Le volume horaire est obligatoire pour cette affectation."},
    )
    starts_on = forms.DateField(
        label="Début de l'affectation",
        required=False,
        widget=forms.DateInput(attrs={"class": INPUT_CLASS, "type": "date"}),
    )
    ends_on = forms.DateField(
        label="Fin de l'affectation",
        required=False,
        widget=forms.DateInput(attrs={"class": INPUT_CLASS, "type": "date"}),
    )

    def __init__(self, *args, branch=None, instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.branch = branch
        self.instance = instance
        if branch is not None:
            self.fields["class_id"].queryset = AcademicClass.objects.select_related(
                "programme", "academic_year"
            ).filter(branch=branch, is_active=True, is_archived=False).order_by(
                "level", "programme__title", "id"
            )
            self.fields["class_id"].widget.attrs.update(
                {
                    "hx-get": f"{reverse('accounts_portal:director_teacher_ec_options')}?mode=assignment",
                    "hx-target": "#director-teacher-assignment-ec-field",
                    "hx-swap": "innerHTML",
                    "hx-trigger": "change",
                    "hx-indicator": "#director-teacher-assignment-loading",
                }
            )
        if instance is not None and not self.is_bound:
            self.initial.update(
                {
                    "class_id": instance.academic_class_id,
                    "ec_id": instance.ec_id,
                    "room_label": instance.room_label,
                    "planned_hours": instance.planned_hours,
                    "starts_on": instance.starts_on,
                    "ends_on": instance.ends_on,
                }
            )
        raw_class = self.data.get(self.add_prefix("class_id")) if self.is_bound else self.initial.get("class_id")
        raw_class = getattr(raw_class, "pk", raw_class)
        if branch is not None and str(raw_class or "").isdigit():
            self.fields["ec_id"].queryset = EC.objects.select_related(
                "ue", "ue__semester"
            ).filter(
                ue__semester__academic_class_id=int(raw_class),
                ue__semester__academic_class__branch=branch,
            ).exclude(structure_status=EC.STRUCTURE_ARCHIVED).order_by(
                "ue__semester__number", "ue__code", "title", "id"
            )

    def clean(self):
        cleaned = super().clean()
        academic_class = cleaned.get("class_id")
        ec = cleaned.get("ec_id")
        if academic_class and ec and ec.ue.semester.academic_class_id != academic_class.id:
            self.add_error("ec_id", "Cette matière n'appartient pas à la classe choisie.")
        starts_on = cleaned.get("starts_on")
        ends_on = cleaned.get("ends_on")
        if starts_on and ends_on and ends_on < starts_on:
            self.add_error("ends_on", "La date de fin doit être postérieure au début.")
        return cleaned


class DirectorTeacherDocumentForm(forms.Form):
    teacher_id = TeacherChoiceField(
        label="Enseignant",
        queryset=get_user_model().objects.none(),
        empty_label="Choisir un enseignant",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    document_type = forms.ChoiceField(
        label="Type de pièce",
        choices=TeacherDocument.DOCUMENT_CHOICES,
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    note = forms.CharField(
        label="Référence ou commentaire",
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Ex. Diplôme original vérifié"}),
    )
    file = forms.FileField(
        label="Fichier",
        validators=[FileExtensionValidator(["pdf", "png", "jpg", "jpeg", "doc", "docx"])],
        widget=forms.ClearableFileInput(attrs={"class": FILE_INPUT_CLASS, "accept": ".pdf,.png,.jpg,.jpeg,.doc,.docx"}),
    )

    def __init__(self, *args, branch=None, selected_teacher_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        if branch is not None:
            self.fields["teacher_id"].queryset = get_user_model().objects.select_related(
                "profile"
            ).filter(
                is_active=True, profile__position="teacher", profile__branch=branch
            ).order_by("first_name", "last_name", "username")
        if selected_teacher_id and not self.is_bound:
            self.initial["teacher_id"] = selected_teacher_id

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        if uploaded.size > 10 * 1024 * 1024:
            raise forms.ValidationError("Le fichier ne doit pas dépasser 10 Mo.")
        return uploaded


class DirectorAdministrativeDocumentForm(forms.Form):
    doc_type = forms.ChoiceField(
        label="Type de document",
        choices=AdministrativeDocument.TYPE_CHOICES,
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    reference = forms.CharField(
        label="Référence",
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Ex. DE/2026/001"}),
    )
    title = forms.CharField(
        label="Objet",
        max_length=200,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Objet précis du document"}),
    )
    recipients = forms.CharField(
        label="Destinataires",
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Ex. Tous les enseignants de L1"}),
    )
    body = forms.CharField(
        label="Corps du document",
        widget=forms.Textarea(attrs={"class": TEXTAREA_CLASS, "rows": 10, "placeholder": "Rédigez le contenu officiel du document"}),
    )

    def __init__(self, *args, instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = instance
        if instance is not None and not self.is_bound:
            self.initial.update(
                {
                    "doc_type": instance.doc_type,
                    "reference": instance.reference,
                    "title": instance.title,
                    "recipients": instance.recipients,
                    "body": instance.body,
                }
            )


class DirectorProgrammeClassForm(forms.Form):
    programme = ProgrammeChoiceField(
        label="Programme",
        queryset=Programme.objects.none(),
        empty_label="Choisir un programme",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    academic_year = forms.ModelChoiceField(
        label="Année académique",
        queryset=AcademicYear.objects.none(),
        empty_label="Choisir une année",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    level = forms.CharField(
        label="Niveau",
        max_length=10,
        widget=forms.TextInput(
            attrs={"class": INPUT_CLASS, "placeholder": "Ex. L1, L2, M1"}
        ),
    )
    validation_threshold = forms.DecimalField(
        label="Seuil de validation",
        required=False,
        min_value=Decimal("0.01"),
        max_value=Decimal("20.00"),
        max_digits=4,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={"class": INPUT_CLASS, "step": "0.01", "placeholder": "Ex. 10"}
        ),
    )

    def __init__(self, *args, branch=None, instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.branch = branch
        self.instance = instance
        self.fields["programme"].queryset = Programme.objects.select_related("cycle").filter(
            is_active=True
        ).order_by("cycle__name", "title", "id")
        self.fields["academic_year"].queryset = AcademicYear.objects.order_by(
            "-start_date", "-id"
        )
        if instance is not None and not self.is_bound:
            self.initial.update(
                {
                    "programme": instance.programme_id,
                    "academic_year": instance.academic_year_id,
                    "level": instance.level,
                    "validation_threshold": instance.validation_threshold,
                }
            )

    def clean_level(self):
        return self.cleaned_data["level"].strip().upper()

    def clean(self):
        cleaned = super().clean()
        programme = cleaned.get("programme")
        academic_year = cleaned.get("academic_year")
        level = cleaned.get("level")
        if self.branch and programme and academic_year and level:
            duplicate = AcademicClass.objects.filter(
                branch=self.branch,
                programme=programme,
                academic_year=academic_year,
                level__iexact=level,
                is_archived=False,
            )
            if self.instance is not None:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                self.add_error(
                    "level",
                    "Une classe existe déjà pour ce programme, cette année et ce niveau.",
                )
        return cleaned


class DirectorBranchSettingsForm(forms.ModelForm):
    """The small, shared branch profile a Director of Studies may maintain.

    Academic rules deliberately do not live here: they are configured on the
    academic class / its maquette, where the grading engine already reads them.
    """

    class Meta:
        model = Branch
        fields = ("address", "city", "phone", "email")
        widgets = {
            "address": forms.Textarea(
                attrs={
                    "class": TEXTAREA_CLASS,
                    "rows": 3,
                    "placeholder": "Adresse ou indication utile pour l'annexe",
                }
            ),
            "city": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "phone": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "email": forms.EmailInput(attrs={"class": INPUT_CLASS}),
        }
        labels = {
            "address": "Adresse",
            "city": "Ville",
            "phone": "Téléphone",
            "email": "E-mail de l'annexe",
        }


class DirectorSemesterForm(forms.Form):
    number = forms.TypedChoiceField(
        label="Semestre",
        choices=Semester.SEMESTER_CHOICES,
        coerce=int,
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )

    def __init__(self, *args, branch=None, academic_class=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.branch = branch
        self.academic_class = academic_class
        existing = set()
        if academic_class is not None and academic_class.branch_id == getattr(branch, "id", None):
            existing = set(academic_class.semesters.values_list("number", flat=True))
        choices = [choice for choice in Semester.SEMESTER_CHOICES if choice[0] not in existing]
        self.fields["number"].choices = choices
        self.has_available_semester = bool(choices)


class DirectorUEForm(forms.Form):
    semester = SemesterChoiceField(
        label="Semestre",
        queryset=Semester.objects.none(),
        empty_label="Choisir un semestre",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    code = forms.CharField(
        label="Code UE",
        max_length=50,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Ex. UE101"}),
    )
    title = forms.CharField(
        label="Intitulé",
        max_length=255,
        widget=forms.TextInput(
            attrs={"class": INPUT_CLASS, "placeholder": "Intitulé de l'unité d'enseignement"}
        ),
    )

    def __init__(self, *args, branch=None, academic_class=None, **kwargs):
        super().__init__(*args, **kwargs)
        if branch is not None and academic_class is not None:
            self.fields["semester"].queryset = Semester.objects.filter(
                academic_class=academic_class,
                academic_class__branch=branch,
            ).order_by("number", "id")

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()


class DirectorECForm(forms.Form):
    ue = UEChoiceField(
        label="Unité d'enseignement",
        queryset=UE.objects.none(),
        empty_label="Choisir une UE",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    title = forms.CharField(
        label="Intitulé de la matière",
        max_length=255,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Ex. Comptabilité générale"}),
    )
    coefficient = forms.DecimalField(
        label="Coefficient",
        min_value=Decimal("0.01"),
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01", "placeholder": "1"}),
    )
    credit_required = forms.DecimalField(
        label="Crédits",
        min_value=Decimal("0.01"),
        max_value=Decimal("6.00"),
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01", "placeholder": "3"}),
    )

    def __init__(self, *args, branch=None, academic_class=None, **kwargs):
        super().__init__(*args, **kwargs)
        if branch is not None and academic_class is not None:
            self.fields["ue"].queryset = UE.objects.select_related("semester").filter(
                semester__academic_class=academic_class,
                semester__academic_class__branch=branch,
            ).exclude(structure_status=UE.STRUCTURE_ARCHIVED).order_by(
                "semester__number", "code", "id"
            )

    def clean(self):
        cleaned = super().clean()
        coefficient = cleaned.get("coefficient")
        credits = cleaned.get("credit_required")
        if coefficient is not None and credits is not None and credits < coefficient:
            self.add_error(
                "credit_required",
                "Les crédits ne peuvent pas être inférieurs au coefficient.",
            )
        return cleaned


class DirectorEvaluationForm(forms.Form):
    campaign = forms.ModelChoiceField(
        label="Campagne calendrier",
        queryset=EvaluationCampaign.objects.none(),
        empty_label="Choisir une campagne publiée",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    title = forms.CharField(
        label="Intitulé",
        max_length=255,
        widget=forms.TextInput(
            attrs={"class": INPUT_CLASS, "placeholder": "Intitulé de l'évaluation"}
        ),
    )
    event_type = forms.ChoiceField(
        label="Type",
        choices=(
            (AcademicScheduleEvent.EVENT_TYPE_EXAM, "Examen"),
            (AcademicScheduleEvent.EVENT_TYPE_PRACTICAL, "Évaluation pratique"),
        ),
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    class_id = AcademicClassChoiceField(
        label="Classe",
        queryset=AcademicClass.objects.none(),
        empty_label="Choisir une classe",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    ec = ECChoiceField(
        label="Matière (EC)",
        queryset=EC.objects.none(),
        empty_label="Choisir d'abord une classe",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    teacher = TeacherChoiceField(
        label="Enseignant",
        queryset=get_user_model().objects.none(),
        empty_label="Choisir un enseignant",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    start_datetime = forms.DateTimeField(
        label="Début",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"class": INPUT_CLASS, "type": "datetime-local"},
        ),
    )
    end_datetime = forms.DateTimeField(
        label="Fin",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"class": INPUT_CLASS, "type": "datetime-local"},
        ),
    )
    location = forms.CharField(
        label="Salle",
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={"class": INPUT_CLASS, "placeholder": "Salle ou amphithéâtre"}
        ),
    )
    description = forms.CharField(
        label="Contenu évalué",
        required=False,
        widget=forms.Textarea(
            attrs={"class": TEXTAREA_CLASS, "rows": 3, "placeholder": "Contenu ou consignes"}
        ),
    )

    def __init__(self, *args, branch=None, selected_class_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.branch = branch
        if branch is None:
            return

        self.fields["class_id"].queryset = (
            AcademicClass.objects.select_related("programme", "academic_year")
            .filter(branch=branch, is_active=True)
            .order_by("level", "programme__title", "name", "id")
        )
        self.fields["campaign"].queryset = (
            EvaluationCampaign.objects.select_related("calendar_entry")
            .filter(branch=branch)
            .exclude(status__in=[EvaluationCampaign.STATUS_CANCELLED, EvaluationCampaign.STATUS_CLOSED])
            .order_by("calendar_entry__start_datetime", "id")
        )
        self.fields["class_id"].widget.attrs.update(
            {
                "hx-get": reverse("accounts_portal:director_evaluation_ec_options"),
                "hx-target": "#director-evaluation-ec-field",
                "hx-swap": "innerHTML",
                "hx-trigger": "change",
                "hx-indicator": "#director-evaluation-form-loading",
            }
        )
        self.fields["teacher"].queryset = (
            get_user_model()
            .objects.select_related("profile")
            .filter(is_active=True, profile__position="teacher", profile__branch=branch)
            .order_by("first_name", "last_name", "username")
        )

        raw_class_id = selected_class_id
        if self.is_bound:
            raw_class_id = self.data.get(self.add_prefix("class_id"))
        elif self.initial.get("class_id"):
            raw_class_id = getattr(self.initial["class_id"], "pk", self.initial["class_id"])

        if str(raw_class_id or "").isdigit():
            self.fields["ec"].queryset = (
                EC.objects.select_related("ue", "ue__semester")
                .filter(
                    ue__semester__academic_class_id=int(raw_class_id),
                    ue__semester__academic_class__branch=branch,
                )
                .order_by("ue__semester__number", "ue__code", "title", "id")
            )

    @property
    def has_teachers(self):
        return self.fields["teacher"].queryset.exists()

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_datetime")
        end = cleaned.get("end_datetime")
        academic_class = cleaned.get("class_id")
        campaign = cleaned.get("campaign")
        ec = cleaned.get("ec")
        teacher = cleaned.get("teacher")

        if start and end and end <= start:
            self.add_error("end_datetime", "La fin doit être postérieure au début.")
        if academic_class and ec and ec.ue.semester.academic_class_id != academic_class.id:
            self.add_error("ec", "Cette matière n'appartient pas à la classe sélectionnée.")
        if teacher and self.branch and teacher.profile.branch_id != self.branch.id:
            self.add_error("teacher", "Cet enseignant n'appartient pas à votre annexe.")
        if campaign and academic_class:
            included = campaign.scopes.filter(academic_class=academic_class, included=True).exists()
            excluded = campaign.scopes.filter(academic_class=academic_class, included=False).exists()
            if not included or excluded:
                self.add_error("class_id", "Cette classe ne fait pas partie de la campagne sélectionnée.")
        return cleaned


class DirectorExamSessionForm(forms.Form):
    title = forms.CharField(
        label="Intitulé",
        max_length=255,
        widget=forms.TextInput(
            attrs={"class": INPUT_CLASS, "placeholder": "Session d'examens du semestre"}
        ),
    )
    event_type = forms.ChoiceField(
        label="Type",
        choices=(),
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    start_date = forms.DateField(
        label="Date de début",
        widget=forms.DateInput(attrs={"class": INPUT_CLASS, "type": "date"}),
    )
    end_date = forms.DateField(
        label="Date de fin",
        widget=forms.DateInput(attrs={"class": INPUT_CLASS, "type": "date"}),
    )
    description = forms.CharField(
        label="Informations complémentaires",
        required=False,
        widget=forms.Textarea(
            attrs={"class": TEXTAREA_CLASS, "rows": 3, "placeholder": "Informations utiles pour la session"}
        ),
    )

    def __init__(self, *args, event_type_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["event_type"].choices = event_type_choices

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "La date de fin ne peut pas précéder la date de début.")
        return cleaned


class DirectorWeeklyScheduleSlotForm(forms.Form):
    weekday = forms.TypedChoiceField(
        label="Jour",
        choices=WeeklyScheduleSlot.WEEKDAY_CHOICES[:6],
        coerce=int,
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    start_time = forms.TimeField(
        label="Heure de début",
        input_formats=["%H:%M", "%H:%M:%S"],
        widget=forms.TimeInput(attrs={"class": INPUT_CLASS, "type": "time", "step": "300"}),
    )
    end_time = forms.TimeField(
        label="Heure de fin",
        input_formats=["%H:%M", "%H:%M:%S"],
        widget=forms.TimeInput(attrs={"class": INPUT_CLASS, "type": "time", "step": "300"}),
    )
    ec_id = ECChoiceField(
        label="Matière",
        queryset=EC.objects.none(),
        empty_label="Choisir la matière",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
        error_messages={"invalid_choice": "Cette matière n'appartient pas à la classe sélectionnée."},
    )
    teacher_id = TeacherChoiceField(
        label="Enseignant",
        queryset=get_user_model().objects.none(),
        empty_label="Choisir l'enseignant",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
        error_messages={"invalid_choice": "Cet enseignant n'appartient pas à votre annexe."},
    )
    room = forms.CharField(
        label="Salle",
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={"class": INPUT_CLASS, "placeholder": "Ex. Salle A12"}
        ),
    )

    def __init__(
        self, *args, branch=None, academic_class=None, instance=None, **kwargs
    ):
        if instance is not None and not args and "data" not in kwargs:
            initial = kwargs.setdefault("initial", {})
            initial.update(
                {
                    "weekday": instance.weekday,
                    "start_time": instance.start_time,
                    "end_time": instance.end_time,
                    "ec_id": instance.ec_id,
                    "teacher_id": instance.teacher_id,
                    "room": instance.room,
                }
            )
        super().__init__(*args, **kwargs)
        self.branch = branch
        self.academic_class = academic_class
        self.instance = instance
        if branch is None or academic_class is None:
            return
        self.fields["ec_id"].queryset = (
            EC.objects.select_related("ue", "ue__semester")
            .filter(
                ue__semester__academic_class=academic_class,
                ue__semester__academic_class__branch=branch,
            )
            .exclude(structure_status=EC.STRUCTURE_ARCHIVED)
            .order_by("ue__semester__number", "ue__code", "title", "id")
        )
        self.fields["teacher_id"].queryset = (
            get_user_model()
            .objects.select_related("profile")
            .filter(
                is_active=True,
                profile__position="teacher",
                profile__branch=branch,
            )
            .order_by("first_name", "last_name", "username")
        )

    @property
    def has_subjects(self):
        return self.fields["ec_id"].queryset.exists()

    @property
    def has_teachers(self):
        return self.fields["teacher_id"].queryset.exists()

    def clean(self):
        cleaned = super().clean()
        start_time = cleaned.get("start_time")
        end_time = cleaned.get("end_time")
        if start_time and end_time and end_time <= start_time:
            self.add_error(
                "end_time", "L'heure de fin doit être postérieure à l'heure de début."
            )
        return cleaned


class DirectorScheduleEventForm(DirectorWeeklyScheduleSlotForm):
    """Edition d'une séance réelle, isolée par date et non par modèle hebdomadaire."""

    date = forms.DateField(
        label="Date de la séance",
        widget=forms.DateInput(attrs={"class": INPUT_CLASS, "type": "date"}),
    )

    def __init__(self, *args, instance=None, **kwargs):
        if instance is not None and not args and "data" not in kwargs:
            local_start = timezone.localtime(instance.start_datetime)
            local_end = timezone.localtime(instance.end_datetime)
            initial = kwargs.setdefault("initial", {})
            initial.update(
                {
                    "date": local_start.date(),
                    "start_time": local_start.time(),
                    "end_time": local_end.time(),
                    "ec_id": instance.ec_id,
                    "teacher_id": instance.teacher_id,
                    "room": instance.location,
                }
            )
        super().__init__(*args, instance=None, **kwargs)
        self.fields.pop("weekday", None)


class DirectorTransferForm(forms.Form):
    enrollment_id = EnrollmentChoiceField(
        label="Étudiant et classe actuelle",
        queryset=AcademicEnrollment.objects.none(),
        required=False,
        empty_label="Choisir un étudiant",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    transfer_type = forms.ChoiceField(
        label="Type de transfert",
        choices=TransferRequest.TYPE_CHOICES,
        widget=forms.RadioSelect(),
    )
    target_class_id = AcademicClassChoiceField(
        label="Classe de destination",
        queryset=AcademicClass.objects.none(),
        required=False,
        empty_label="Choisir une autre classe",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    target_school_name = forms.CharField(
        label="Établissement de destination",
        max_length=180,
        required=False,
        widget=forms.TextInput(
            attrs={"class": INPUT_CLASS, "placeholder": "Nom complet de l'établissement"}
        ),
    )
    school_city = forms.CharField(
        label="Ville de l'établissement",
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Ex. Bamako"}),
    )
    destination_programme = forms.CharField(
        label="Programme visé dans l'établissement",
        max_length=180,
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Programme ou filière de destination"}),
    )
    destination_level = forms.CharField(
        label="Niveau visé",
        max_length=40,
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Ex. L2"}),
    )
    academic_check_completed = forms.BooleanField(label="Contrôle académique terminé", required=False)
    administrative_check_completed = forms.BooleanField(label="Contrôle administratif terminé", required=False)
    financial_check_completed = forms.BooleanField(label="Quitus financier vérifié", required=False)
    origin_school_name = forms.CharField(
        label="Établissement d'origine",
        max_length=180,
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Nom complet de l'établissement d'origine"}),
    )
    first_name = forms.CharField(label="Prénom du candidat", max_length=150, required=False, widget=forms.TextInput(attrs={"class": INPUT_CLASS}))
    last_name = forms.CharField(label="Nom du candidat", max_length=150, required=False, widget=forms.TextInput(attrs={"class": INPUT_CLASS}))
    birth_date = forms.DateField(label="Date de naissance", required=False, widget=forms.DateInput(attrs={"class": INPUT_CLASS, "type": "date"}))
    birth_place = forms.CharField(label="Lieu de naissance", max_length=150, required=False, widget=forms.TextInput(attrs={"class": INPUT_CLASS}))
    gender = forms.ChoiceField(label="Genre", required=False, choices=(("", "Choisir"), ("male", "Masculin"), ("female", "Féminin")), widget=forms.Select(attrs={"class": INPUT_CLASS}))
    phone = forms.CharField(label="Téléphone", max_length=30, required=False, widget=forms.TextInput(attrs={"class": INPUT_CLASS}))
    email = forms.EmailField(label="Adresse e-mail", required=False, widget=forms.EmailInput(attrs={"class": INPUT_CLASS}))
    address = forms.CharField(label="Adresse", max_length=255, required=False, widget=forms.TextInput(attrs={"class": INPUT_CLASS}))
    city = forms.CharField(label="Ville de résidence", max_length=100, required=False, widget=forms.TextInput(attrs={"class": INPUT_CLASS}))
    country = forms.CharField(label="Pays", max_length=100, required=False, initial="Mali", widget=forms.TextInput(attrs={"class": INPUT_CLASS}))
    equivalence_notes = forms.CharField(
        label="Éléments d'équivalence à étudier",
        required=False,
        widget=forms.Textarea(attrs={"class": TEXTAREA_CLASS, "rows": 3, "placeholder": "Niveau acquis, crédits, unités validées et réserves éventuelles"}),
    )
    academic_decision_reference = forms.CharField(
        label="Référence de décision académique",
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Facultatif"}),
    )
    effective_date = forms.DateField(label="Date d'effet", required=False, widget=forms.DateInput(attrs={"class": INPUT_CLASS, "type": "date"}))
    previous_academic_year = forms.CharField(label="Dernière année fréquentée", max_length=30, required=False, widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Ex. 2025-2026"}))
    last_validated_semester = forms.CharField(label="Dernier semestre validé", max_length=30, required=False, widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Ex. S2"}))
    external_student_number = forms.CharField(label="Matricule dans l'établissement d'origine", max_length=80, required=False, widget=forms.TextInput(attrs={"class": INPUT_CLASS}))
    recognised_equivalences = forms.CharField(label="Équivalences reconnues", required=False, widget=forms.Textarea(attrs={"class": TEXTAREA_CLASS, "rows": 2}))
    subjects_to_retake = forms.CharField(label="EC / matières à reprendre", required=False, widget=forms.Textarea(attrs={"class": TEXTAREA_CLASS, "rows": 2}))
    academic_reservations = forms.CharField(label="Réserves académiques", required=False, widget=forms.Textarea(attrs={"class": TEXTAREA_CLASS, "rows": 2}))
    reason = forms.CharField(
        label="Motif et observations",
        required=True,
        widget=forms.Textarea(
            attrs={"class": TEXTAREA_CLASS, "rows": 4, "placeholder": "Expliquez la décision pédagogique et les éléments du dossier"}
        ),
    )
    attachment = forms.FileField(
        label="Pièce justificative",
        required=False,
        validators=[FileExtensionValidator(["pdf", "jpg", "jpeg", "png"])],
        widget=forms.ClearableFileInput(
            attrs={"class": FILE_INPUT_CLASS, "accept": ".pdf,.jpg,.jpeg,.png"}
        ),
    )

    def __init__(self, *args, branch=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.branch = branch
        if branch is None:
            return
        self.fields["enrollment_id"].queryset = (
            AcademicEnrollment.objects.select_related("student", "academic_class")
            .filter(branch=branch, is_active=True, is_archived=False)
            .order_by("academic_class__level", "student__last_name", "student__first_name", "student__username")
        )
        self.fields["target_class_id"].queryset = (
            AcademicClass.objects.select_related("programme", "academic_year")
            .filter(branch=branch, is_active=True, is_archived=False)
            .order_by("level", "programme__title", "id")
        )

    def clean_attachment(self):
        attachment = self.cleaned_data.get("attachment")
        if attachment and attachment.size > 5 * 1024 * 1024:
            raise forms.ValidationError("La pièce jointe ne doit pas dépasser 5 Mo.")
        return attachment

    def clean(self):
        cleaned = super().clean()
        enrollment = cleaned.get("enrollment_id")
        transfer_type = cleaned.get("transfer_type")
        target_class = cleaned.get("target_class_id")
        target_school = (cleaned.get("target_school_name") or "").strip()
        if transfer_type == TransferRequest.TYPE_INTERNAL:
            if enrollment is None:
                self.add_error("enrollment_id", "Choisissez l'étudiant concerné.")
            if target_class is None:
                self.add_error("target_class_id", "Choisissez la classe de destination.")
            elif enrollment and target_class.pk == enrollment.academic_class_id:
                self.add_error("target_class_id", "La destination doit être différente de la classe actuelle.")
            elif enrollment and target_class.academic_year_id != enrollment.academic_year_id:
                self.add_error("target_class_id", "Le transfert de classe doit rester dans la même année académique.")
            elif enrollment and target_class.level.strip().upper() != enrollment.academic_class.level.strip().upper():
                self.add_error("target_class_id", "Le niveau acquis doit rester identique. Le passage d'année est un autre workflow.")
            elif enrollment and target_class.programme_id != enrollment.programme_id:
                self.add_error("target_class_id", "Le transfert interclasse doit rester dans la même filière. Utilisez un reclassement académique motivé.")
            cleaned["target_school_name"] = ""
        elif transfer_type == TransferRequest.TYPE_OUTGOING:
            if enrollment is None:
                self.add_error("enrollment_id", "Choisissez l'étudiant concerné.")
            if not target_school:
                self.add_error("target_school_name", "Indiquez l'école de destination.")
            cleaned["target_class_id"] = None
        elif transfer_type == TransferRequest.TYPE_INCOMING:
            cleaned["enrollment_id"] = None
            cleaned["target_school_name"] = ""
            required_fields = (
                "origin_school_name", "first_name", "last_name", "birth_date",
                "birth_place", "gender", "phone", "email", "target_class_id",
            )
            for field_name in required_fields:
                if not cleaned.get(field_name):
                    self.add_error(field_name, "Ce champ est obligatoire pour un transfert entrant.")
        return cleaned


class DirectorTransferDocumentForm(forms.Form):
    document_type = forms.ChoiceField(
        label="Type de pièce",
        choices=TransferDocument.TYPE_CHOICES,
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    title = forms.CharField(
        label="Intitulé",
        max_length=180,
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Nom du document"}),
    )
    file = forms.FileField(
        label="Fichier",
        validators=[FileExtensionValidator(["pdf", "jpg", "jpeg", "png"])],
        widget=forms.ClearableFileInput(attrs={"class": FILE_INPUT_CLASS}),
    )

    def clean_file(self):
        file = self.cleaned_data["file"]
        if file.size > 10 * 1024 * 1024:
            raise forms.ValidationError("La pièce ne doit pas dépasser 10 Mo.")
        return file


class DirectorInternalMessageForm(forms.Form):
    AUDIENCE_CHOICES = (
        ("individual", "Utilisateurs sélectionnés"),
        ("staff", "Personnel de l'annexe"),
        ("teachers", "Tous les enseignants"),
        ("students", "Tous les étudiants"),
        ("classes", "Étudiants par classe"),
        ("programmes", "Étudiants par programme"),
    )
    ROLE_CHOICES = (
        ("teacher", "Enseignants"),
        ("secretary", "Secrétariat"),
        ("academic_supervisor", "Surveillance académique"),
        ("branch_manager", "Gestionnaires"),
        ("annex_manager", "Gestionnaires d'annexe"),
        ("finance_manager", "Finance"),
        ("admissions", "Admissions"),
        ("it_support", "Support informatique"),
    )

    audience = forms.ChoiceField(
        label="Cible principale",
        choices=AUDIENCE_CHOICES,
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    recipients = forms.ModelMultipleChoiceField(
        label="Utilisateurs",
        queryset=get_user_model().objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": INPUT_CLASS, "size": 7}),
    )
    target_classes = forms.ModelMultipleChoiceField(
        label="Classes",
        queryset=AcademicClass.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": INPUT_CLASS, "size": 5}),
    )
    target_programmes = forms.ModelMultipleChoiceField(
        label="Programmes",
        queryset=Programme.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": INPUT_CLASS, "size": 5}),
    )
    target_roles = forms.MultipleChoiceField(
        label="Fonctions du personnel",
        choices=ROLE_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple(),
    )
    title = forms.CharField(
        label="Objet",
        max_length=255,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Objet du message"}),
    )
    body = forms.CharField(
        label="Message",
        widget=forms.Textarea(
            attrs={"class": TEXTAREA_CLASS, "rows": 7, "placeholder": "Rédigez un message précis et directement exploitable"}
        ),
    )
    priority = forms.ChoiceField(
        label="Priorité",
        choices=(
            (NotificationMessage.PRIORITY_NORMAL, "Normale"),
            (NotificationMessage.PRIORITY_HIGH, "Importante"),
            (NotificationMessage.PRIORITY_CRITICAL, "Urgente"),
        ),
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    attachment = forms.FileField(
        label="Pièce jointe",
        required=False,
        validators=[FileExtensionValidator(["pdf", "doc", "docx", "xls", "xlsx", "jpg", "jpeg", "png"])],
        widget=forms.ClearableFileInput(attrs={"class": FILE_INPUT_CLASS}),
    )

    def __init__(self, *args, branch=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if branch is None:
            return
        from notification_center.services.internal_messaging import (
            can_send_collective_message,
        )

        if user is not None and not can_send_collective_message(user):
            # Envoi individuel uniquement pour les comptes non habilites
            # aux messages collectifs (regle portee par le service).
            self.fields["audience"].choices = self.AUDIENCE_CHOICES[:1]
            del self.fields["target_classes"]
            del self.fields["target_programmes"]
            del self.fields["target_roles"]
        queryset = (
            get_user_model().objects.select_related("profile")
            .filter(
                Q(profile__branch=branch)
                | Q(academic_enrollments__branch=branch, academic_enrollments__is_active=True, academic_enrollments__is_archived=False)
            )
            .filter(is_active=True)
            .distinct()
            .order_by("first_name", "last_name", "username")
        )
        if user and user.pk:
            queryset = queryset.exclude(pk=user.pk)
        self.fields["recipients"].queryset = queryset
        if "target_classes" in self.fields:
            self.fields["target_classes"].queryset = AcademicClass.objects.filter(
                branch=branch, is_active=True, is_archived=False
            ).select_related("programme").order_by("level", "programme__title")
        if "target_programmes" in self.fields:
            self.fields["target_programmes"].queryset = Programme.objects.filter(
                academic_classes__branch=branch,
                academic_classes__is_active=True,
                academic_classes__is_archived=False,
            ).distinct().order_by("title")

    def clean_attachment(self):
        attachment = self.cleaned_data.get("attachment")
        if attachment and attachment.size > 10 * 1024 * 1024:
            raise forms.ValidationError("La pièce jointe ne doit pas dépasser 10 Mo.")
        return attachment

    def clean(self):
        cleaned = super().clean()
        audience = cleaned.get("audience")
        if audience == "individual" and not cleaned.get("recipients"):
            self.add_error("recipients", "Sélectionnez au moins un utilisateur.")
        elif audience == "classes" and not cleaned.get("target_classes"):
            self.add_error("target_classes", "Sélectionnez au moins une classe.")
        elif audience == "programmes" and not cleaned.get("target_programmes"):
            self.add_error("target_programmes", "Sélectionnez au moins un programme.")
        return cleaned
