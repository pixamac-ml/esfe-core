from django_components import component


@component.register("progress_ring")
class ProgressRing(component.Component):
    template_name = "dashboard/progress_ring.html"

    def get_context_data(
        self,
        value=0,
        max_value=100,
        size=64,
        stroke_width=6,
        label="",
        tone="primary",
        **kwargs,
    ):
        radius = (size - stroke_width) // 2
        circumference = 2 * 3.14159 * radius
        percentage = min(max((value / max_value) * 100, 0), 100) if max_value > 0 else 0
        offset = circumference - (percentage / 100) * circumference

        tone_colors = {
            "success": "var(--success)",
            "warning": "var(--warning)",
            "danger": "var(--danger)",
            "primary": "var(--school-primary)",
            "info": "var(--info)",
        }

        return {
            "value": value,
            "max_value": max_value,
            "size": size,
            "center": size / 2,
            "stroke_width": stroke_width,
            "radius": radius,
            "circumference": circumference,
            "percentage": int(percentage),
            "offset": offset,
            "label": label,
            "tone": tone,
            "stroke_color": tone_colors.get(tone, tone_colors["primary"]),
            **kwargs,
        }
