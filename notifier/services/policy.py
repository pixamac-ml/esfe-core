from notifier.models import NotificationMessage


POLICY_REGISTRY = {
    "candidature_submitted": {
        "audience": "candidate",
        "channels": (
            NotificationMessage.CHANNEL_IN_APP,
            NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL,
        ),
        "priority": NotificationMessage.PRIORITY_NORMAL,
        "channel_family": "email_transactional",
        "realtime_behavior": "none",
    },
    "candidature_accepted": {
        "audience": "candidate",
        "channels": (
            NotificationMessage.CHANNEL_IN_APP,
            NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL,
        ),
        "priority": NotificationMessage.PRIORITY_HIGH,
        "channel_family": "email_transactional",
        "realtime_behavior": "none",
    },
    "candidature_rejected": {
        "audience": "candidate",
        "channels": (
            NotificationMessage.CHANNEL_IN_APP,
            NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL,
        ),
        "priority": NotificationMessage.PRIORITY_HIGH,
        "channel_family": "email_transactional",
        "realtime_behavior": "none",
    },
    "document_missing": {
        "audience": "candidate",
        "channels": (
            NotificationMessage.CHANNEL_IN_APP,
            NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL,
        ),
        "priority": NotificationMessage.PRIORITY_HIGH,
        "channel_family": "system_alert",
        "realtime_behavior": "none",
    },
    "inscription_created": {
        "audience": "candidate",
        "channels": (
            NotificationMessage.CHANNEL_IN_APP,
            NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL,
        ),
        "priority": NotificationMessage.PRIORITY_NORMAL,
        "channel_family": "email_transactional",
        "realtime_behavior": "none",
    },
    "inscription_payment_pending": {
        "audience": "candidate",
        "channels": (
            NotificationMessage.CHANNEL_IN_APP,
            NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL,
        ),
        "priority": NotificationMessage.PRIORITY_NORMAL,
        "channel_family": "email_transactional",
        "realtime_behavior": "none",
    },
    "inscription_partial_payment": {
        "audience": "candidate",
        "channels": (
            NotificationMessage.CHANNEL_IN_APP,
            NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL,
        ),
        "priority": NotificationMessage.PRIORITY_NORMAL,
        "channel_family": "email_transactional",
        "realtime_behavior": "none",
    },
    "inscription_active": {
        "audience": "candidate",
        "channels": (
            NotificationMessage.CHANNEL_IN_APP,
            NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL,
        ),
        "priority": NotificationMessage.PRIORITY_HIGH,
        "channel_family": "email_transactional",
        "realtime_behavior": "none",
    },
    "payment_validated": {
        "audience": "student",
        "channels": (
            NotificationMessage.CHANNEL_IN_APP,
        ),
        "priority": NotificationMessage.PRIORITY_HIGH,
        "channel_family": "notification_in_app",
        "realtime_behavior": "silent",
    },
    "first_payment_validated_staff": {
        "audience": "staff_finance",
        "channels": (
            NotificationMessage.CHANNEL_IN_APP,
        ),
        "priority": NotificationMessage.PRIORITY_HIGH,
        "channel_family": "finance_alert",
        "realtime_behavior": "silent",
    },
    "salary_available": {
        "audience": "staff_payroll",
        "channels": (
            NotificationMessage.CHANNEL_IN_APP,
            NotificationMessage.CHANNEL_WEBSOCKET,
        ),
        "priority": NotificationMessage.PRIORITY_HIGH,
        "channel_family": "notification_in_app",
        "realtime_behavior": "useful",
    },
    "shop_purchase_validated": {
        "audience": "shop_buyer",
        "channels": (
            NotificationMessage.CHANNEL_IN_APP,
            NotificationMessage.CHANNEL_WEBSOCKET,
        ),
        "priority": NotificationMessage.PRIORITY_HIGH,
        "channel_family": "notification_in_app",
        "realtime_behavior": "useful",
    },
    "community_new_topic": {
        "audience": "community_user",
        "channels": (
            NotificationMessage.CHANNEL_IN_APP,
            NotificationMessage.CHANNEL_WEBSOCKET,
        ),
        "priority": NotificationMessage.PRIORITY_NORMAL,
        "channel_family": "notification_in_app",
        "realtime_behavior": "useful",
    },
    "community_new_answer": {
        "audience": "community_user",
        "channels": (
            NotificationMessage.CHANNEL_IN_APP,
            NotificationMessage.CHANNEL_WEBSOCKET,
        ),
        "priority": NotificationMessage.PRIORITY_HIGH,
        "channel_family": "notification_in_app",
        "realtime_behavior": "useful",
    },
    "community_reply_to_reply": {
        "audience": "community_user",
        "channels": (
            NotificationMessage.CHANNEL_IN_APP,
            NotificationMessage.CHANNEL_WEBSOCKET,
        ),
        "priority": NotificationMessage.PRIORITY_HIGH,
        "channel_family": "notification_in_app",
        "realtime_behavior": "useful",
    },
    "community_upvote": {
        "audience": "community_user",
        "channels": (
            NotificationMessage.CHANNEL_IN_APP,
        ),
        "priority": NotificationMessage.PRIORITY_LOW,
        "channel_family": "notification_in_app",
        "realtime_behavior": "none",
    },
    "community_accepted_answer": {
        "audience": "community_user",
        "channels": (
            NotificationMessage.CHANNEL_IN_APP,
            NotificationMessage.CHANNEL_WEBSOCKET,
        ),
        "priority": NotificationMessage.PRIORITY_HIGH,
        "channel_family": "notification_in_app",
        "realtime_behavior": "useful",
    },
}


def resolve_channel_policy(event_type, *, default_channels, default_priority, metadata=None):
    policy = POLICY_REGISTRY.get(event_type, {})
    resolved_metadata = dict(metadata or {})
    resolved_metadata.setdefault("channel_family", policy.get("channel_family", "notification_in_app"))
    resolved_metadata.setdefault("realtime_behavior", policy.get("realtime_behavior", "none"))
    resolved_metadata.setdefault("policy_audience", policy.get("audience", "generic"))

    channels = tuple(policy.get("channels") or default_channels)

    email_channel = NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL
    if email_channel in default_channels and email_channel not in channels:
        channels = channels + (email_channel,)

    return {
        "channels": channels,
        "priority": policy.get("priority") or default_priority,
        "metadata": resolved_metadata,
    }
