from django import template

register = template.Library()

# Couleurs unifiees pour les statuts du cycle de vie SecretaryStatusMixin
_STATUS_BADGE_CLASSES = {
    "pending": "bg-[color:var(--accent-bg)] text-[color:var(--muted-2)]",
    "in_progress": "bg-blue-50 text-blue-700",
    "transferred": "bg-violet-50 text-violet-700",
    "completed": "bg-green-50 text-green-700",
    "cancelled": "bg-red-50 text-red-700",
    "archived": "bg-[color:var(--accent-bg)] text-[color:var(--muted-2)]",
}

# Couleurs unifiees pour les priorites (RegistryEntry: low/normal/high/immediate,
# SecretaryTask: low/medium/high/urgent)
_PRIORITY_PILL_CLASSES = {
    "low": "bg-[color:var(--accent-bg)] text-[color:var(--muted-2)]",
    "normal": "bg-blue-50 text-blue-700",
    "medium": "bg-blue-50 text-blue-700",
    "high": "bg-amber-50 text-amber-700",
    "urgent": "bg-red-50 text-red-700",
    "immediate": "bg-red-50 text-red-700",
}

_URGENT_PRIORITIES = {"immediate", "urgent"}


@register.filter
def status_badge_class(status):
    return _STATUS_BADGE_CLASSES.get(status, "sg-badge-gray")


@register.filter
def priority_pill_class(priority):
    return _PRIORITY_PILL_CLASSES.get(priority, "sg-priority-normal")


@register.filter
def is_urgent_priority(priority):
    return priority in _URGENT_PRIORITIES


# Mapping des statuts vers les tons du composant status_badge
_STATUS_TONES = {
    "pending": "neutral",
    "in_progress": "info",
    "transferred": "primary",
    "completed": "success",
    "cancelled": "danger",
    "archived": "neutral",
}


@register.filter
def status_tone(status):
    return _STATUS_TONES.get(status, "neutral")
