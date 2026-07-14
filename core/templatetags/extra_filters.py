from django import template

register = template.Library()


@register.filter
def index(list_like, i):
    """Accès par index : {{ list|index:0 }}"""
    try:
        return list_like[i]
    except (IndexError, TypeError):
        return None


@register.filter
def divisibleby(value, arg):
    """Retourne True si value est divisible par arg"""
    try:
        return int(value) % int(arg) == 0
    except (ValueError, ZeroDivisionError):
        return False


@register.filter
def duration_minutes(log):
    """Retourne la durée d'un cahier de texte en minutes."""
    from datetime import datetime, date

    if not log or not getattr(log, "start_time", None) or not getattr(log, "end_time", None):
        return 0
    if log.end_time <= log.start_time:
        return 0
    base = log.date or date.min
    start = datetime.combine(base, log.start_time)
    end = datetime.combine(base, log.end_time)
    return int((end - start).total_seconds() // 60)