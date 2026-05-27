from django import forms

from academics.models import AcademicClass, AcademicScheduleEvent


INPUT_CLASS = "w-full rounded-xl border border-slate-200 px-4 py-3 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary"
TEXTAREA_CLASS = "w-full rounded-xl border border-slate-200 px-4 py-3 text-sm min-h-[90px] focus:ring-2 focus:ring-primary/20 focus:border-primary"


def _style_form_fields(form):
    for field in form.fields.values():
        widget = field.widget
        widget.attrs["class"] = TEXTAREA_CLASS if isinstance(widget, forms.Textarea) else INPUT_CLASS


class LessonObservationForm(forms.Form):
    academic_class = forms.ModelChoiceField(queryset=AcademicClass.objects.none())
    event = forms.ModelChoiceField(queryset=AcademicScheduleEvent.objects.none(), required=False)
    title = forms.CharField(max_length=180)
    details = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}), required=False)

    def __init__(self, *args, branch=None, **kwargs):
        super().__init__(*args, **kwargs)
        if branch:
            self.fields["academic_class"].queryset = AcademicClass.objects.filter(
                branch=branch,
                is_active=True,
            ).select_related("programme", "academic_year")
            self.fields["event"].queryset = AcademicScheduleEvent.objects.filter(branch=branch).select_related(
                "academic_class",
                "teacher",
                "ec",
            )
        _style_form_fields(self)


# Compatibilite d'import pour les anciens modules: ces formulaires ne ciblent
# plus les modeles supprimes ClassPresenceCheck / SurveillanceNote.
SurveillanceNoteForm = LessonObservationForm
ClassPresenceCheckForm = LessonObservationForm
