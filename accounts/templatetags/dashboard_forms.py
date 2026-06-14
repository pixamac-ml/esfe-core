from django import template

register = template.Library()

FIELD_ICONS = {
    "period_month": "fa-calendar-days",
    "base_salary": "fa-sack-dollar",
    "allowances": "fa-circle-plus",
    "deductions": "fa-circle-minus",
    "advances": "fa-hand-holding-dollar",
    "hourly_rate": "fa-clock",
    "validated_hours": "fa-stopwatch",
    "adjustments": "fa-sliders",
    "bank_transfer_amount": "fa-building-columns",
    "bank_name": "fa-building-columns",
    "reference": "fa-hashtag",
    "transfer_date": "fa-calendar-check",
    "amount": "fa-money-bill-wave",
    "proof": "fa-paperclip",
    "comment": "fa-comment",
    "title": "fa-heading",
    "category": "fa-tags",
    "expense_date": "fa-calendar-day",
    "supplier": "fa-truck",
    "receipt": "fa-paperclip",
    "movement_type": "fa-right-left",
    "source": "fa-layer-group",
    "label": "fa-tag",
    "movement_date": "fa-calendar-day",
    "donor_name": "fa-user",
    "date": "fa-calendar-day",
    "motif": "fa-comment-dots",
    "payment_method": "fa-credit-card",
    "description": "fa-align-left",
    "receipt_number": "fa-hashtag",
    "notes": "fa-note-sticky",
    "academic_level": "fa-layer-group",
    "academic_class": "fa-chalkboard-user",
}


@register.filter
def field_icon(field_name):
    return FIELD_ICONS.get(field_name, "fa-pen")


@register.filter
def widget_type(field):
    return field.field.widget.__class__.__name__
