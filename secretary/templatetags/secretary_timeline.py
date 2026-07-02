from django import template

from secretary.models import RegistryEntry

register = template.Library()

# Libelles FR des actions enregistrees dans RegistryEntry.history
_HISTORY_ACTION_LABELS = {
    "creation": "Creation de l'entree",
    "prise_en_charge": "Prise en charge",
    "mise_a_jour": "Mise a jour des informations",
    "changement_statut": "Changement de statut",
    "traite": "Marquee comme traitee",
    "archive": "Archivee",
    "backfill": "Initialisation de l'historique",
}

_HISTORY_ACTION_ICONS = {
    "creation": "circle-plus",
    "prise_en_charge": "hand",
    "mise_a_jour": "pen",
    "changement_statut": "arrow-right-left",
    "traite": "check",
    "archive": "archive",
    "backfill": "history",
}

_STATUS_LABELS = dict(RegistryEntry.STATUS_CHOICES)


@register.filter
def history_action_label(action):
    return _HISTORY_ACTION_LABELS.get(action, action or "Evenement")


@register.filter
def history_action_icon(action):
    return _HISTORY_ACTION_ICONS.get(action, "fa-circle-dot")


@register.filter
def registry_status_label(status):
    return _STATUS_LABELS.get(status, status or "-")


@register.filter
def history_actor_label(username):
    return username or "Systeme"
