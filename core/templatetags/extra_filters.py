from django import template

register = template.Library()

@register.filter
def zip(a, b):
    return zip(a, b)


from django import template

register = template.Library()

@register.filter
def divisibleby(value, arg):
    """Retourne True si value est divisible par arg"""
    try:
        return int(value) % int(arg) == 0
    except (ValueError, ZeroDivisionError):
        return False