from django import forms
from django.utils import timezone

from .models import Appointment, DocumentReceipt, RegistryEntry, SecretaryTask, VisitorLog


class SecretaryBaseForm(forms.ModelForm):
    def _apply_widget_classes(self):
        for name, field in self.fields.items():
            widget = field.widget
            css_class = widget.attrs.get("class", "")
            widget.attrs["class"] = f"{css_class} secretary-input".strip()
            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("rows", 4)
            if field.required:
                widget.attrs.setdefault("required", "required")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_widget_classes()


class RegistryEntryForm(SecretaryBaseForm):
    class Meta:
        model = RegistryEntry
        fields = [
            "title",
            "description",
            "entry_type",
            "related_student",
            "related_staff",
            "status",
        ]


class AppointmentForm(SecretaryBaseForm):
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
