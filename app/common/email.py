"""Outbound transactional email over SMTP.

Sending is synchronous (smtplib) and meant to run inside Celery tasks, never on the request path.
In development and test an unset SMTP_HOST logs the message instead of sending it, so flows like
password reset can be exercised locally; elsewhere it raises, so a misconfiguration is not silent.
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from app.config import settings

logger = logging.getLogger("email")


class EmailNotConfiguredError(RuntimeError):
    pass


def build_message(to_address: str, subject: str, text_body: str, html_body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = formataddr((settings.EMAIL_FROM_NAME, settings.EMAIL_FROM_ADDRESS))
    msg["To"] = to_address
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain=settings.EMAIL_FROM_ADDRESS.rsplit("@", 1)[-1])
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    return msg


def send_email(to_address: str, subject: str, text_body: str, html_body: str) -> None:
    """Send one email. Raises on any delivery failure so the caller can retry."""
    msg = build_message(to_address, subject, text_body, html_body)

    if not settings.SMTP_HOST:
        if settings.ENVIRONMENT in ("development", "test"):
            logger.warning(
                "SMTP_HOST is not set; email NOT sent (development only).\nTo: %s\nSubject: %s\n\n%s",
                to_address, subject, text_body,
            )
            return
        raise EmailNotConfiguredError("SMTP_HOST is not configured; cannot send email")

    timeout = settings.SMTP_TIMEOUT_SECONDS
    context = ssl.create_default_context()
    if settings.SMTP_SECURITY == "ssl":
        server: smtplib.SMTP = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=timeout, context=context)
    else:
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=timeout)
    with server:
        if settings.SMTP_SECURITY == "starttls":
            server.starttls(context=context)
        if settings.SMTP_USERNAME:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD or "")
        server.send_message(msg)
    logger.info("Sent email '%s' to %s", subject, to_address)
