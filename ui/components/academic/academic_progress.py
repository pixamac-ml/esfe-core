from django_components import component


@component.register("academic_progress")
class AcademicProgress(component.Component):
    """Barre de progression scolaire : taux de réussite, avancement, etc."""

    template_name = "academic/academic_progress.html"

    def get_context_data(
        self,
        label="",
        value=0,
        max_value=100,
        size="md",
        tone="primary",
        show_value=True,
        **kwargs,
    ):
        try:
            normalized_value = int(value)
        except (TypeError, ValueError):
            normalized_value = 0
        max_val = int(max_value or 100)
        normalized_value = max(0, min(normalized_value, max_val))
        pct = round(normalized_value / max_val * 100) if max_val else 0
        return {
            "label": label,
            "value": normalized_value,
            "max_value": max_val,
            "pct": pct,
            "size": size,
            "tone": tone,
            "show_value": show_value,
            **kwargs,
        }
