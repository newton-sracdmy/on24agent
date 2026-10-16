"""Asynchronous Celery tasks for transactional account emails (password reset and confirmation)."""

import html
import logging
import smtplib

from app.common.email import send_email
from app.config import settings
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Transient SMTP/network failures are retried with exponential backoff (30s, 60s, 120s, ...)
_RETRYABLE = (smtplib.SMTPException, OSError)


def _greeting(full_name: str) -> str:
    first = (full_name or "").strip().split(" ", 1)[0]
    return f"Hi {first}," if first else "Hi,"


def _html_page(paragraphs: list[str]) -> str:
    body = "".join(f'<p style="margin:0 0 16px">{p}</p>' for p in paragraphs)
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.5;'
        f'color:#0f172a;max-width:560px">{body}</div>'
    )


def render_password_reset_email(full_name: str, reset_url: str, expires_minutes: int) -> tuple[str, str, str]:
    """Return (subject, text_body, html_body) for a password reset email."""
    app_name = settings.EMAIL_FROM_NAME
    subject = f"Reset your {app_name} password"
    text_body = (
        f"{_greeting(full_name)}\n\n"
        f"We received a request to reset the password for your {app_name} account.\n"
        f"Open this link to choose a new password:\n\n{reset_url}\n\n"
        f"The link expires in {expires_minutes} minutes and can only be used once.\n\n"
        "If you didn't request this, you can ignore this email; your password will not change.\n"
    )
    safe_url = html.escape(reset_url, quote=True)
    html_body = _html_page([
        html.escape(_greeting(full_name)),
        f"We received a request to reset the password for your {html.escape(app_name)} account.",
        f'<a href="{safe_url}" style="display:inline-block;padding:10px 18px;background:#059669;color:#ffffff;'
        'text-decoration:none;border-radius:8px;font-weight:bold">Reset password</a>',
        f'Or paste this link into your browser:<br><span style="word-break:break-all">{safe_url}</span>',
        f"The link expires in {expires_minutes} minutes and can only be used once.",
        "If you didn't request this, you can ignore this email; your password will not change.",
    ])
    return subject, text_body, html_body


def render_password_changed_email(full_name: str) -> tuple[str, str, str]:
    """Return (subject, text_body, html_body) confirming a completed password reset."""
    app_name = settings.EMAIL_FROM_NAME
    subject = f"Your {app_name} password was changed"
    text_body = (
        f"{_greeting(full_name)}\n\n"
        f"The password for your {app_name} account was just changed, and all devices were signed out.\n\n"
        "If you didn't do this, reset your password immediately and contact support.\n"
    )
    html_body = _html_page([
        html.escape(_greeting(full_name)),
        f"The password for your {html.escape(app_name)} account was just changed, and all devices were signed out.",
        "If you didn't do this, reset your password immediately and contact support.",
    ])
    return subject, text_body, html_body


@celery_app.task(
    name="app.workers.tasks.email_tasks.send_password_reset_email",
    autoretry_for=_RETRYABLE, retry_backoff=30, retry_backoff_max=600, retry_jitter=True, max_retries=5,
)
def send_password_reset_email(to_address: str, full_name: str, reset_url: str, expires_minutes: int) -> None:
    send_email(to_address, *render_password_reset_email(full_name, reset_url, expires_minutes))


@celery_app.task(
    name="app.workers.tasks.email_tasks.send_password_changed_email",
    autoretry_for=_RETRYABLE, retry_backoff=30, retry_backoff_max=600, retry_jitter=True, max_retries=5,
)
def send_password_changed_email(to_address: str, full_name: str) -> None:
    send_email(to_address, *render_password_changed_email(full_name))
