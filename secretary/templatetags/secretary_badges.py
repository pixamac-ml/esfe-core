from django import template

register = template.Library()

# Couleurs unifiees pour les statuts du cycle de vie SecretaryStatusMixin
_STATUS_BADGE_CLASSES = {
    "pending": "sg-badge-gray",
    "in_progress": "sg-badge-blue",
    "transferred": "sg-badge-violet",
    "completed": "sg-badge-green",
    "cancelled": "sg-badge-red",
    "archived": "sg-badge-gray",
}

# Couleurs unifiees pour les priorites (RegistryEntry: low/normal/high/immediate,
# SecretaryTask: low/medium/high/urgent)
_PRIORITY_PILL_CLASSES = {
    "low": "sg-priority-low",
    "normal": "sg-priority-normal",
    "medium": "sg-priority-normal",
    "high": "sg-priority-high",
    "urgent": "sg-priority-immediate",
    "immediate": "sg-priority-immediate",
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
