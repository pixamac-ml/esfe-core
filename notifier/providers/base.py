from dataclasses import dataclass


@dataclass
class ProviderResult:
    status: str
    provider: str
    provider_message_id: str = ""


class BaseEmailProvider:
    provider_name = "base"

    def send_notification(self, message):
        raise NotImplementedError
