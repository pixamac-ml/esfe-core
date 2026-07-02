"""Import legacy communication tables after the old Django app was removed."""

import json

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from notifier.models import DeliveryAttempt, NotificationEvent, NotificationMessage


LEGACY_EVENT_TABLE = "communication_communicationevent"
LEGACY_MESSAGE_TABLE = "communication_communicationnotification"
LEGACY_DELIVERY_TABLE = "communication_communicationdelivery"


def _json_value(value, default):
    if value in (None, ""):
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return default
    return value


def _table_rows(table_name):
    quote = connection.ops.quote_name
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT * FROM {quote(table_name)} ORDER BY {quote('id')}")
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


class Command(BaseCommand):
    help = "Import communication events, notifications and deliveries into notifier"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report importable rows without writing")

    def handle(self, *args, **options):
        tables = set(connection.introspection.table_names())
        required = {LEGACY_EVENT_TABLE, LEGACY_MESSAGE_TABLE, LEGACY_DELIVERY_TABLE}
        missing = required - tables
        if missing:
            self.stdout.write(
                self.style.WARNING(
                    "Legacy communication tables are absent; nothing to import: "
                    + ", ".join(sorted(missing))
                )
            )
            return

        events = _table_rows(LEGACY_EVENT_TABLE)
        messages = _table_rows(LEGACY_MESSAGE_TABLE)
        deliveries = _table_rows(LEGACY_DELIVERY_TABLE)
        self.stdout.write(
            f"Legacy rows found: {len(events)} event(s), {len(messages)} notification(s), "
            f"{len(deliveries)} delivery attempt(s)."
        )
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run: no data written."))
            return

        with transaction.atomic():
            event_map = self._import_events(events)
            message_map = self._import_messages(messages, event_map)
            self._import_deliveries(deliveries, message_map)

        self.stdout.write(self.style.SUCCESS("Legacy communication import complete."))

    def _import_events(self, rows):
        mapping = {}
        for row in rows:
            legacy_id = row["id"]
            metadata = _json_value(row.get("metadata"), {})
            metadata = {**metadata, "legacy_communication_event_id": legacy_id}
            event = NotificationEvent.objects.filter(
                metadata__legacy_communication_event_id=legacy_id,
            ).first()
            if event is None:
                event = NotificationEvent.objects.create(
                    event_type=row["event_type"],
                    source_app=row.get("source_app") or "core",
                    actor_id=row.get("actor_id"),
                    recipient_id=row.get("recipient_id"),
                    payload=_json_value(row.get("payload"), {}),
                    metadata=metadata,
                    status=row.get("status") or NotificationEvent.STATUS_PENDING,
                    processed_at=row.get("processed_at"),
                )
                NotificationEvent.objects.filter(pk=event.pk).update(
                    created_at=row.get("created_at"),
                    updated_at=row.get("updated_at"),
                )
            mapping[legacy_id] = event
        return mapping

    def _import_messages(self, rows, event_map):
        mapping = {}
        for row in rows:
            legacy_id = row["id"]
            message = NotificationMessage.objects.filter(
                legacy_source="communication.CommunicationNotification",
                legacy_object_id=str(legacy_id),
            ).first()
            if message is None:
                message = NotificationMessage.objects.create(
                    event=event_map.get(row.get("event_id")),
                    actor_id=row.get("actor_id"),
                    recipient_id=row.get("recipient_id"),
                    title=row["title"],
                    body=row.get("body") or "",
                    notification_type=row["notification_type"],
                    event_type=row["event_type"],
                    channel=row["channel"],
                    priority=row.get("priority") or NotificationMessage.PRIORITY_NORMAL,
                    status=row.get("status") or NotificationMessage.STATUS_PENDING,
                    metadata=_json_value(row.get("metadata"), {}),
                    legacy_source="communication.CommunicationNotification",
                    legacy_object_id=str(legacy_id),
                    read_at=row.get("read_at"),
                    sent_at=row.get("sent_at"),
                    delivered_at=row.get("delivered_at"),
                )
                NotificationMessage.objects.filter(pk=message.pk).update(
                    created_at=row.get("created_at"),
                    updated_at=row.get("updated_at"),
                )
            mapping[legacy_id] = message
        return mapping

    def _import_deliveries(self, rows, message_map):
        for row in rows:
            message = message_map.get(row.get("notification_id"))
            if message is None:
                continue
            legacy_id = row["id"]
            snapshot = _json_value(row.get("payload_snapshot"), {})
            snapshot = {**snapshot, "legacy_communication_delivery_id": legacy_id}
            if DeliveryAttempt.objects.filter(
                payload_snapshot__legacy_communication_delivery_id=legacy_id,
            ).exists():
                continue
            delivery = DeliveryAttempt.objects.create(
                message=message,
                channel=row["channel"],
                provider=row.get("provider") or "",
                status=row.get("status") or NotificationMessage.STATUS_PENDING,
                attempt_count=row.get("attempt_count") or 0,
                provider_message_id=row.get("provider_message_id") or "",
                payload_snapshot=snapshot,
                error_message=row.get("error_message") or "",
                sent_at=row.get("sent_at"),
                delivered_at=row.get("delivered_at"),
            )
            DeliveryAttempt.objects.filter(pk=delivery.pk).update(
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at"),
            )
