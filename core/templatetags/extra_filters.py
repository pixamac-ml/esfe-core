from django import template

register = template.Library()

@register.filter
def zip(a, b):
    return zip(a, b)
