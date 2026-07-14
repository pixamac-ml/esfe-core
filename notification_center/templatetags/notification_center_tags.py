from django import template

from notification_center.presentation import get_safe_action_url


register = template.Library()


@register.simple_tag(takes_context=True)
def notification_action_url(context, notification):
    return get_safe_action_url(notification, context.get("request"))
