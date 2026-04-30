from django import forms
from django.contrib.auth import get_user_model

from academics.models import AcademicClass, AcademicScheduleEvent, ClassPresenceCheck, SurveillanceNote


User = get_user_model()

INPUT_CLASS = "w-full rounded-xl border border-slate-200 px-4 py-3 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary"
TEXTAREA_CLASS = "w-full rounded-xl border border-slate-200 px-4 py-3 text-sm min-h-[90px] focus:ring-2 focus:ring-primary/20 focus:border-primary"


def _style_form_fields(form):
    for name, field in form.fields.items():
        widget = field.widget
        if isinstance(widget, forms.Select):
            widget.attrs["class"] = INPUT_CLASS
        elif isinstance(widget, forms.SelectMultiple):
            widget.attrs["class"] = INPUT_CLASS
        elif isinstance(widget, forms.Textarea):
            widget.attrs["class"] = TEXTAREA_CLASS
        else:
            widget.attrs["class"] = INPUT_CLASS


class SurveillanceNoteForm(forms.ModelForm):
    class Meta:
        model = SurveillanceNote
        fields = ["note_type", "severity", "title", "details", "academic_class", "event", "teacher", "student"]
        widgets = {
            "details": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, branch=None, **kwargs):
        super().__init__(*args, **kwargs)
        if branch:
            self.fields["academic_class"].queryset = AcademicClass.objects.filter(branch=branch, is_active=True).select_related("programme", "academic_year")
            self.fields["event"].queryset = AcademicScheduleEvent.objects.filter(branch=branch).select_related("academic_class", "teacher", "ec")
        else:
            self.fields["academic_class"].queryset = AcademicClass.objects.none()
            self.fields["event"].queryset = AcademicScheduleEvent.objects.none()
        self.fields["teacher"].queryset = User.objects.filter(profile__role="teacher").select_related("profile")
        self.fields["student"].queryset = User.objects.filter(profile__role="student").select_related("profile")
        _style_form_fields(self)


class ClassPresenceCheckForm(forms.ModelForm):
    class Meta:
        model = ClassPresenceCheck
        fields = ["academic_class", "event", "expected_count", "present_count", "late_count", "absent_count", "note"]
        widgets = {
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, branch=None, **kwargs):
        super().__init__(*args, **kwargs)
        if branch:
            self.fields["academic_class"].queryset = AcademicClass.objects.filter(branch=branch, is_active=True).select_related("programme", "academic_year")
            self.fields["event"].queryset = AcademicScheduleEvent.objects.filter(branch=branch).select_related("academic_class", "teacher", "ec")
        else:
            self.fields["academic_class"].queryset = AcademicClass.objects.none()
            self.fields["event"].queryset = AcademicScheduleEvent.objects.none()
        _style_form_fields(self)
