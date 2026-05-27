import asyncio
import sys


class IgnoreClientCancelledError:
    """Drop noisy ASGI logs for HTTP clients that disconnected mid-request."""

    def filter(self, record):
        exc_info = getattr(record, "exc_info", None)
        if exc_info is True:
            exc_info = sys.exc_info()
        if isinstance(exc_info, tuple) and len(exc_info) >= 2:
            exc_type, exc_value = exc_info[:2]
            if exc_type is asyncio.CancelledError or isinstance(exc_value, asyncio.CancelledError):
                return False

        message = record.getMessage()
        if "asyncio.exceptions.CancelledError" in message or "CancelledError" == message.strip():
            return False
        return True
