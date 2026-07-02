from notifier.models import NotificationMessage
from notifier.services.audience import resolve_platform_users
from notifier.services import NotificationBus

from marketing.models import Announcement, DispatchLog
from .campaign_service import create_dispatch_log


def resolve_announcement_recipients(announcement):
    return resolve_platform_users(
        audience_scope=announcement.audience_scope,
        branch_ids=list(announcement.branches.values_list("id", flat=True)),
        programme_ids=list(announcement.formations.values_list("id", flat=True)),
        cycle_ids=list(announcement.cycles.values_list("id", flat=True)),
        class_ids=list(announcement.classes.values_list("id", flat=True)),
        role_tokens=announcement.target_roles or [],
        user_types=announcement.target_user_types or [],
    )


def publish_announcement(announcement, *, actor=None):
    recipients = resolve_announcement_recipients(announcement)
    channels = [NotificationMessage.CHANNEL_IN_APP, NotificationMessage.CHANNEL_WEBSOCKET]
    if "email" in (announcement.channels or []):
        channels.append(NotificationMessage.CHANNEL_EMAIL_MARKETING)

    created_count = 0
    for recipient in recipients.iterator():
        NotificationBus.notify(
            recipient=recipient,
            actor=actor,
            event_type="marketing.announcement",
            title=announcement.title,
            body=announcement.content,
            source_app="marketing",
            priority=announcement.priority,
            channels=tuple(channels),
            metadata={
                "announcement_id": announcement.id,
                "show_popup": announcement.show_popup,
                "is_blocking_popup": announcement.is_blocking_popup,
                "audience": announcement.audience_label,
                "audience_scope": announcement.audience_scope,
                "branch_ids": list(announcement.branches.values_list("id", flat=True)),
                "programme_ids": list(announcement.formations.values_list("id", flat=True)),
                "cycle_ids": list(announcement.cycles.values_list("id", flat=True)),
                "class_ids": list(announcement.classes.values_list("id", flat=True)),
            },
            legacy_source="marketing_announcement",
            legacy_object_id=str(announcement.id),
        )
        created_count += 1

    create_dispatch_log(
        announcement=announcement,
        channel="dashboard_popup" if announcement.show_popup else "dashboard_notification",
        actor=actor,
        status=DispatchLog.STATUS_SENT,
        recipients_count=created_count,
    )
    return created_count
