"""Transactional email.

Falls back to logging the link when SMTP is unconfigured, so local development
never needs a mail server — the verification URL appears in the API logs.
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


async def send_verification(to: str, token: str) -> None:
    link = f"{settings.web_url}/verify-email?token={token}"
    await _send(
        to,
        "Verify your email",
        f"Welcome to {settings.app_name}.\n\n"
        f"Confirm your email address to activate your account:\n{link}\n\n"
        f"This link expires in 24 hours.",
    )


async def send_password_reset(to: str, token: str) -> None:
    link = f"{settings.web_url}/reset-password?token={token}"
    await _send(
        to,
        "Reset your password",
        f"Someone asked to reset the password for this account.\n\n"
        f"If it was you, set a new password here:\n{link}\n\n"
        f"This link expires in 1 hour. If it wasn't you, ignore this email.",
    )


async def _send(to: str, subject: str, body: str) -> None:
    if not settings.smtp_host:
        # Development: the link is what matters, not the delivery.
        log.info("email.console_fallback", to=to, subject=subject, body=body)
        return

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    # smtplib is blocking; keep it off the event loop.
    await asyncio.to_thread(_deliver, message)


def _deliver(message: EmailMessage) -> None:
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)
    except Exception as exc:  # noqa: BLE001 — a mail outage must not 500 signup
        log.error("email.send_failed", to=message["To"], error=str(exc))
