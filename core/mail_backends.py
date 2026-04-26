import smtplib

from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend as DjangoSMTPEmailBackend


class StableSMTPEmailBackend(DjangoSMTPEmailBackend):
    """
    SMTP backend with a deterministic, RFC-safe EHLO hostname.

    Some local network setups expose an invalid FQDN containing commas or
    multiple domains. Gmail rejects that EHLO payload before STARTTLS/login.
    """

    def __init__(self, *args, local_hostname=None, **kwargs):
        super().__init__(*args, **kwargs)
        configured_hostname = local_hostname or getattr(
            settings, "EMAIL_LOCAL_HOSTNAME", "localhost"
        )
        self.local_hostname = self._normalize_local_hostname(configured_hostname)

    def _normalize_local_hostname(self, value):
        hostname = (value or "").strip().rstrip(".")
        if not hostname:
            return "localhost"

        # Reject values that Gmail commonly refuses during EHLO negotiation.
        invalid_chars = {",", " ", "\t", "\r", "\n", "/"}
        if any(char in hostname for char in invalid_chars):
            return "localhost"

        labels = hostname.split(".")
        for label in labels:
            if not label:
                return "localhost"
            if label.startswith("-") or label.endswith("-"):
                return "localhost"
            if not all(char.isalnum() or char == "-" for char in label):
                return "localhost"

        return hostname

    def open(self):
        if self.connection:
            return False

        connection_params = {"local_hostname": self.local_hostname}
        if self.timeout is not None:
            connection_params["timeout"] = self.timeout
        if self.use_ssl:
            connection_params["context"] = self.ssl_context

        try:
            self.connection = self.connection_class(
                self.host, self.port, **connection_params
            )
            if not self.use_ssl and self.use_tls:
                self.connection.starttls(context=self.ssl_context)
            if self.username and self.password:
                self.connection.login(self.username, self.password)
            return True
        except OSError:
            if not self.fail_silently:
                raise

