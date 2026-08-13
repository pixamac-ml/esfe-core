from notification_center.services import (
    resolve_internal_message_recipients,
    send_internal_message,
)


def send_director_internal_message(
    *, user, branch, recipients, title, body, priority, audience="individual",
    class_ids=None, programme_ids=None, role_tokens=None, attachment=None,
    parent_message=None,
):
    resolved = resolve_internal_message_recipients(
        sender=user,
        branch=branch,
        direct_recipient_ids=[recipient.pk for recipient in recipients],
        audience=audience,
        class_ids=class_ids,
        programme_ids=programme_ids,
        role_tokens=role_tokens,
    )
    return send_internal_message(
        sender=user,
        branch=branch,
        recipients=resolved,
        title=title,
        body=body,
        priority=priority,
        audience=audience,
        attachment=attachment,
        parent_message=parent_message,
    )
