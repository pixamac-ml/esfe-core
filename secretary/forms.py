from django import forms
from django.utils import timezone
from django.contrib.auth import get_user_model

from accounts.dashboards.helpers import get_user_branch, is_global_viewer
from .selectors import get_active_students, get_documents_queryset, get_registry_queryset
from .models import Appointment, DocumentReceipt, RegistryEntry, SecretaryTask, VisitorLog

User = get_user_model()


class SecretaryBaseForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        self.branch = kwargs.pop("branch", None) or get_user_branch(self.user)
        super().__init__(*args, **kwargs)
        self._apply_widget_classes()
        self._apply_scope()

    def _apply_widget_classes(self):
        for name, field in self.fields.items():
            widget = field.widget
            css_class = widget.attrs.get("class", "")
            widget.attrs["class"] = f"{css_class} secretary-input".strip()
            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("rows", 4)
            if field.required:
                widget.attrs.setdefault("required", "required")

    def _branch_user_queryset(self):
        if self.branch:
            return User.objects.filter(profile__branch=self.branch).distinct()
        if self.user and not is_global_viewer(self.user):
            return User.objects.none()
        return User.objects.all()

    def _student_queryset(self):
        if self.branch:
            return get_active_students(branch=self.branch, user=self.user)
        if self.user and not is_global_viewer(self.user):
            return get_active_students(user=self.user)
        return get_active_students(user=self.user)

    def _registry_queryset(self):
        if self.branch:
            return get_registry_queryset(branch=self.branch, user=self.user)
        if self.user and not is_global_viewer(self.user):
            return get_registry_queryset(user=self.user)
        return get_registry_queryset(user=self.user)

    def _apply_scope(self):
        pass


class RegistryEntryForm(SecretaryBaseForm):
    def _apply_scope(self):
        self.fields["related_student"].queryset = self._student_queryset()
        self.fields["related_staff"].queryset = self._branch_user_queryset()
        self.fields["entry_type"].widget.attrs.setdefault("data-registry-routing", "true")
        self.fields["motive"].widget.attrs.setdefault("placeholder", "Motif concret de la venue")
        self.fields["visitor_name"].widget.attrs.setdefault("placeholder", "Nom du parent, visiteur ou deposant")

    class Meta:
        model = RegistryEntry
        fields = [
            "entry_type",
            "visitor_name",
            "visitor_phone",
            "visitor_email",
            "related_student",
            "related_staff",
            "student_class_label",
            "motive",
            "description",
            "priority",
            "target_service",
            "status",
            "exited_at",
            "attachment",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "exited_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def clean_exited_at(self):
        exited_at = self.cleaned_data.get("exited_at")
        if exited_at and timezone.is_naive(exited_at):
            return timezone.make_aware(exited_at, timezone.get_current_timezone())
        return exited_at


class AppointmentForm(SecretaryBaseForm):
    def _apply_scope(self):
        self.fields["related_student"].queryset = self._student_queryset()
        self.fields["assigned_to"].queryset = self._branch_user_queryset()
        self.fields["related_staff"].queryset = self._branch_user_queryset()

    scheduled_at = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )

    class Meta:
        model = Appointment
        fields = [
            "title",
            "person_name",
            "phone",
            "email",
            "reason",
            "scheduled_at",
            "assigned_to",
            "related_student",
            "related_staff",
            "status",
            "notes",
        ]

    def clean_scheduled_at(self):
        scheduled_at = self.cleaned_data["scheduled_at"]
        if timezone.is_naive(scheduled_at):
            scheduled_at = timezone.make_aware(scheduled_at, timezone.get_current_timezone())
        return scheduled_at


class VisitorLogForm(SecretaryBaseForm):
    def _apply_scope(self):
        self.fields["related_student"].queryset = self._student_queryset()
        self.fields["related_staff"].queryset = self._branch_user_queryset()

    arrived_at = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    departed_at = forms.DateTimeField(
        required=False,
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )

    class Meta:
        model = VisitorLog
        fields = [
            "full_name",
            "phone",
            "reason",
            "related_student",
            "related_staff",
            "arrived_at",
            "departed_at",
            "status",
        ]

    def clean_arrived_at(self):
        arrived_at = self.cleaned_data["arrived_at"]
        if timezone.is_naive(arrived_at):
            arrived_at = timezone.make_aware(arrived_at, timezone.get_current_timezone())
        return arrived_at

    def clean_departed_at(self):
        departed_at = self.cleaned_data.get("departed_at")
        if departed_at and timezone.is_naive(departed_at):
            departed_at = timezone.make_aware(departed_at, timezone.get_current_timezone())
        return departed_at


class DocumentReceiptForm(SecretaryBaseForm):
    def _apply_scope(self):
        self.fields["related_student"].queryset = self._student_queryset()
        self.fields["related_registry"].queryset = self._registry_queryset()

    class Meta:
        model = DocumentReceipt
        fields = [
            "title",
            "description",
            "submitted_by_name",
            "submitted_by_phone",
            "related_student",
            "related_registry",
            "status",
            "file",
        ]


class SecretaryTaskForm(SecretaryBaseForm):
    def _apply_scope(self):
        self.fields["assigned_to"].queryset = self._branch_user_queryset()
        self.fields["related_student"].queryset = self._student_queryset()

    class Meta:
        model = SecretaryTask
        fields = [
            "title",
            "description",
            "priority",
            "status",
            "assigned_to",
            "related_student",
            "due_date",
        ]
