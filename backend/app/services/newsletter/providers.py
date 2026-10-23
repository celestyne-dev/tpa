"""Email delivery providers for newsletter and automation mail.

Each provider sends one ``OutgoingEmail`` and returns the provider's message id. A
successful return only means the provider **accepted** the message; delivery, bounces
and complaints are recorded later, and only from provider feedback (see queue.py).

Errors are classified so the queue can retry sensibly:
- ``TransientSendError``: try again later (connection problems, 4xx SMTP replies).
- ``PermanentSendError``: do not retry (5xx replies). ``bounce=True`` when the provider
  rejected the recipient address itself.

Adding an email API provider later means adding a class with the same ``send`` method and
registering it in ``_PROVIDERS``; campaigns, automations and the queue stay unchanged.
"""

from __future__ import annotations

import contextlib
import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage as MimeMessage
from email.utils import formataddr, make_msgid

from flask import current_app

from .config import backend_name

logger = logging.getLogger("tpa.newsletter.mail")


@dataclass
class OutgoingEmail:
    to: str
    subject: str
    html: str
    text: str
    from_name: str
    from_email: str
    reply_to: str = ""
    headers: dict[str, str] = field(default_factory=dict)


class TransientSendError(Exception):
    pass


class PermanentSendError(Exception):
    def __init__(self, message: str, *, bounce: bool = False):
        super().__init__(message)
        self.bounce = bounce


def _mime(message: OutgoingEmail) -> tuple[MimeMessage, str]:
    domain = message.from_email.rsplit("@", 1)[-1] if "@" in message.from_email else None
    message_id = make_msgid(domain=domain)
    mime = MimeMessage()
    mime["From"] = formataddr((message.from_name, message.from_email))
    mime["To"] = message.to
    mime["Subject"] = message.subject
    mime["Message-ID"] = message_id
    if message.reply_to:
        mime["Reply-To"] = message.reply_to
    for name, value in message.headers.items():
        mime[name] = value
    mime.set_content(message.text)
    if message.html:
        mime.add_alternative(message.html, subtype="html")
    return mime, message_id


class SmtpProvider:
    """SMTP with STARTTLS. Reuses one connection for a batch (``open``/``close``)."""

    name = "smtp"
    reports_delivery = False

    def __init__(self):
        cfg = current_app.config
        self.host = cfg.get("NEWSLETTER_SMTP_HOST") or cfg.get("MAIL_SMTP_HOST")
        self.port = cfg.get("NEWSLETTER_SMTP_PORT") or cfg.get("MAIL_SMTP_PORT") or 587
        self.username = cfg.get("NEWSLETTER_SMTP_USERNAME") or cfg.get("MAIL_SMTP_USERNAME")
        self.password = cfg.get("NEWSLETTER_SMTP_PASSWORD") or cfg.get("MAIL_SMTP_PASSWORD")
        self._smtp: smtplib.SMTP | None = None

    def open(self) -> None:
        if self._smtp is not None:
            return
        try:
            smtp = smtplib.SMTP(self.host, self.port, timeout=20)
            smtp.starttls(context=ssl.create_default_context())
            if self.username:
                smtp.login(self.username, self.password)
            self._smtp = smtp
        except smtplib.SMTPAuthenticationError as err:
            # A configuration problem, not a recipient problem: retry with backoff.
            raise TransientSendError("SMTP authentication failed; check the credentials.") from err
        except (OSError, smtplib.SMTPException) as err:
            raise TransientSendError(f"SMTP connection failed ({err.__class__.__name__}).") from err

    def close(self) -> None:
        if self._smtp is not None:
            with contextlib.suppress(OSError, smtplib.SMTPException):
                self._smtp.quit()
            self._smtp = None

    def send(self, message: OutgoingEmail) -> str:
        self.open()
        mime, message_id = _mime(message)
        try:
            refused = self._smtp.send_message(mime)
        except smtplib.SMTPRecipientsRefused as err:
            code = next(iter(err.recipients.values()))[0] if err.recipients else 550
            if 400 <= code < 500:
                raise TransientSendError(f"Recipient temporarily refused ({code}).") from err
            raise PermanentSendError(f"Recipient refused ({code}).", bounce=True) from err
        except (smtplib.SMTPDataError, smtplib.SMTPSenderRefused) as err:
            if 400 <= err.smtp_code < 500:
                raise TransientSendError(f"Temporary SMTP error ({err.smtp_code}).") from err
            raise PermanentSendError(f"SMTP rejected the message ({err.smtp_code}).") from err
        except (OSError, smtplib.SMTPException) as err:
            self._smtp = None
            raise TransientSendError(f"SMTP error ({err.__class__.__name__}).") from err
        if refused:
            raise PermanentSendError("Recipient refused.", bounce=True)
        return message_id.strip("<>")


class ConsoleProvider:
    """Development only: logs the message instead of sending it."""

    name = "development_console"
    reports_delivery = False

    def open(self) -> None: ...

    def close(self) -> None: ...

    def send(self, message: OutgoingEmail) -> str:
        _mime_msg, message_id = _mime(message)
        logger.warning(
            "\n===== DEVELOPMENT NEWSLETTER EMAIL (not sent) =====\nTo: %s\nSubject: %s\n"
            "Headers: %s\n\n%s\n===================================================",
            message.to,
            message.subject,
            message.headers,
            message.text,
        )
        return message_id.strip("<>")


class MemoryProvider:
    """Tests: keeps messages in memory. ``fail_with`` simulates provider errors."""

    name = "memory"
    reports_delivery = False
    outbox: list[OutgoingEmail] = []
    fail_with: list[Exception] = []

    def open(self) -> None: ...

    def close(self) -> None: ...

    def send(self, message: OutgoingEmail) -> str:
        if MemoryProvider.fail_with:
            raise MemoryProvider.fail_with.pop(0)
        MemoryProvider.outbox.append(message)
        return f"memory-{len(MemoryProvider.outbox)}@example.invalid"


class NullProvider:
    name = "not_configured"
    reports_delivery = False

    def open(self) -> None: ...

    def close(self) -> None: ...

    def send(self, message: OutgoingEmail) -> str:
        raise TransientSendError("Email delivery is not configured.")


_PROVIDERS = {"smtp": SmtpProvider, "console": ConsoleProvider, "memory": MemoryProvider}


def get_provider():
    override = current_app.extensions.get("tpa_newsletter_provider")
    if override is not None:
        return override
    name = backend_name()
    if name == "console" and current_app.config.get("ENV_NAME") == "production":
        return NullProvider()
    if name == "memory" and not current_app.testing:
        return NullProvider()
    return _PROVIDERS.get(name, NullProvider)()
