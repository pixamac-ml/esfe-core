from django import template
from django.template.defaultfilters import stringfilter

register = template.Library()

@register.filter
def str_class(obj):
    return obj.__class__.__name__


# ================= MATH FILTERS =================

@register.filter
def multiply(value, arg):
    """Multiplie la valeur par l'argument"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def divide(value, arg):
    """Divise la valeur par l'argument"""
    try:
        arg = float(arg)
        if arg == 0:
            return 0
        return float(value) / arg
    except (ValueError, TypeError):
        return 0


@register.filter
def add(value, arg):
    """Ajoute l'argument à la valeur"""
    try:
        return float(value) + float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def subtract(value, arg):
    """Soustrait l'argument de la valeur"""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0


# ================= STRING FILTERS =================

@register.filter
@stringfilter
def replace(value, arg):
    """Remplace une chaîne par une autre. Usage: {{ value|replace:"old,new" }}"""
    try:
        old, new = arg.split(',')
        return value.replace(old, new)
    except (ValueError, AttributeError):
        return value


@register.filter
def has_group(user, group_name):
    return user.groups.filter(name=group_name).exists()


@register.simple_tag
def get_user_group(user):
    if not user or not user.is_authenticated:
        return None
    return user.groups.first()