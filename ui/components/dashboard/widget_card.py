from django_components import component


@component.register("widget_card")
class WidgetCard(component.Component):
    template_name = "dashboard/widget_card.html"

    def get_context_data(
        self,
        label="",
        value="",
        icon="",
        tone="primary",
        size="lg",
        trend=0,
        trend_label="",
        hint="",
        href="",
        loading=False,
        class_str="",
        **kwargs,
    ):
        tones = {
            "primary": "bg-[color:var(--school-primary-soft)] text-[color:var(--school-primary)]",
            "success": "bg-[color:var(--success-soft)] text-[color:var(--success)]",
            "warning": "bg-[color:var(--warning-soft)] text-[color:var(--warning)]",
            "danger": "bg-[color:var(--danger-soft)] text-[color:var(--danger)]",
            "info": "bg-[color:var(--info-soft)] text-[color:var(--info)]",
            "neutral": "bg-[color:var(--card-soft)] text-[color:var(--muted)]",
        }
        return {
            "label": label,
            "value": value,
            "icon": icon,
            "tone": tone,
            "size": size,
            "trend": trend,
            "trend_label": trend_label,
            "hint": hint,
            "href": href,
            "loading": loading,
            "class_str": class_str,
            "icon_class": tones.get(tone, tones["primary"]),
            "tag_name": "a" if href else "div",
            **kwargs,
        }
