from django import template

register = template.Library()

FIELD_ICONS = {
    "title": "fa-heading",
    "entry_type": "fa-tags",
    "visitor_name": "fa-user",
    "full_name": "fa-user",
    "person_name": "fa-user",
    "submitted_by_name": "fa-user",
    "visitor_phone": "fa-phone",
    "phone": "fa-phone",
    "submitted_by_phone": "fa-phone",
    "visitor_email": "fa-envelope",
    "email": "fa-envelope",
    "related_student": "fa-user-graduate",
    "related_staff": "fa-user-tie",
    "assigned_to": "fa-user-tie",
    "related_registry": "fa-book-open",
    "student_class_label": "fa-chalkboard-user",
    "motive": "fa-comment-dots",
    "reason": "fa-comment-dots",
    "description": "fa-align-left",
    "notes": "fa-note-sticky",
    "priority": "fa-flag",
    "target_service": "fa-building-user",
    "status": "fa-circle-half-stroke",
    "exited_at": "fa-right-from-bracket",
    "scheduled_at": "fa-calendar-day",
    "arrived_at": "fa-right-to-bracket",
    "departed_at": "fa-right-from-bracket",
    "due_date": "fa-calendar-check",
    "attachment": "fa-paperclip",
    "file": "fa-paperclip",
    "first_name": "fa-user",
    "last_name": "fa-id-badge",
    "bio": "fa-align-left",
    "location": "fa-location-dot",
    "address": "fa-map-pin",
    "main_domain": "fa-briefcase",
    "website": "fa-globe",
    "avatar": "fa-image",
}


@register.filter
def field_icon(field_name):
    return FIELD_ICONS.get(field_name, "fa-pen")


@register.filter
def widget_type(field):
    return field.field.widget.__class__.__name__
