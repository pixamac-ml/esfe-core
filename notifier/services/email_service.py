from .bus import NotificationBus


class EmailService:
    @staticmethod
    def send_transactional(**kwargs):
        return NotificationBus.send_email(**kwargs)
