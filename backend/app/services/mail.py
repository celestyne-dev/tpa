"""Email delivery abstraction.

Backends (MAIL_BACKEND):
- "none":    not configured; flows that need email refuse to proceed.
- "console": development only; writes the message (including links) to the
             server log so a developer can complete flows locally. Refused in
             production configuration.
- "memory":  testing; keeps messages in an in-process outbox.
- "smtp":    SMTP with STARTTLS (MAIL_SMTP_* settings).

Messages are never returned through the API.
"""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage

from flask import current_app

from ..utils.errors import APIError

logger = logging.getLogger("tpa.mail")


class MailNotConfiguredError(APIError):
    status_code = 503
    code = "email_not_configured"
    message = (
        "Email delivery is not configured, so links cannot be sent. Configure MAIL_BACKEND, "
        "or create the account with an initial password instead."
    )


class MailDeliveryError(APIError):
    status_code = 502
    code = "email_delivery_failed"
    message = "The email could not be sent. Please try again later."


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text: str


class NullBackend:
    name = "not_configured"

    def send(self, message: EmailMessage) -> None:
        raise MailNotConfiguredError()


class ConsoleBackend:
    """Development-only delivery: the message is written to the Flask server log."""

    name = "development_console"

    def send(self, message: EmailMessage) -> None:
        logger.warning(
            "\n===== DEVELOPMENT EMAIL (not sent) =====\nTo: %s\nSubject: %s\n\n%s\n"
            "========================================",
            message.to,
            message.subject,
            message.text,
        )


class MemoryBackend:
    name = "memory"
    outbox: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        MemoryBackend.outbox.append(message)


class SmtpBackend:
    name = "smtp"

    def send(self, message: EmailMessage) -> None:
        cfg = current_app.config
        mime = MimeMessage()
        mime["From"] = cfg["MAIL_FROM"]
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.text)
        try:
            with smtplib.SMTP(cfg["MAIL_SMTP_HOST"], cfg["MAIL_SMTP_PORT"], timeout=15) as smtp:
                smtp.starttls()
                if cfg.get("MAIL_SMTP_USERNAME"):
                    smtp.login(cfg["MAIL_SMTP_USERNAME"], cfg["MAIL_SMTP_PASSWORD"])
                smtp.send_message(mime)
        except (OSError, smtplib.SMTPException) as err:
            logger.error("SMTP delivery failed: %s", err.__class__.__name__)
            raise MailDeliveryError() from None


_BACKENDS = {
    "none": NullBackend,
    "console": ConsoleBackend,
    "memory": MemoryBackend,
    "smtp": SmtpBackend,
}


def get_backend():
    name = (current_app.config.get("MAIL_BACKEND") or "none").lower()
    if name == "console" and current_app.config.get("ENV_NAME") == "production":
        return NullBackend()  # Defence in depth; production config also rejects it.
    return _BACKENDS.get(name, NullBackend)()


def send(message: EmailMessage) -> str:
    """Send a message; returns the delivery method used (raises if it cannot be sent)."""
    backend = get_backend()
    backend.send(message)
    return backend.name
