from django_components import component


@component.register("pill")
class Pill(component.Component):
    template_name = "atoms/pill.html"

    VARIANTS = {
        "default": "bg-[color:var(--card-soft)] text-[color:var(--muted)] border-[color:var(--line)]",
        "primary": "bg-[color:var(--school-primary-soft)] text-[color:var(--school-primary)] border-[color:var(--school-primary)]/20",
        "success": "bg-[color:var(--success-soft)] text-[color:var(--success)] border-[color:var(--success)]/20",
        "warning": "bg-[color:var(--warning-soft)] text-[color:var(--warning)] border-[color:var(--warning)]/20",
        "danger": "bg-[color:var(--danger-soft)] text-[color:var(--danger)] border-[color:var(--danger)]/20",
        "info": "bg-[color:var(--info-soft)] text-[color:var(--info)] border-[color:var(--info)]/20",
    }

    def get_context_data(self, label="", variant="default", icon="", dismissible=False, dismiss_event="", **kwargs):
        return {
            "label": label,
            "icon": icon,
            "dismissible": dismissible,
            "dismiss_event": dismiss_event or f"pill-dismiss-{label.lower().replace(' ', '-')}",
            "classes": self.VARIANTS.get(variant, self.VARIANTS["default"]),
            **kwargs,
        }
