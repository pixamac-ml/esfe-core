from django_components import component


@component.register("academic_stat_card")
class AcademicStatCard(component.Component):
    """Carte indicateur scolaire : valeur, label, icône, tendance, lien."""

    template_name = "academic/academic_stat_card.html"

    def get_context_data(
        self,
        label="",
        value="",
        icon="",
        trend=0,
        trend_label="",
        href="",
        tone="primary",
        size="md",
        **kwargs,
    ):
        return {
            "label": label,
            "value": value,
            "icon": icon,
            "trend": trend,
            "trend_label": trend_label,
            "href": href,
            "tone": tone,
            "size": size,
            **kwargs,
        }
