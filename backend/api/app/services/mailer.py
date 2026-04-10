import logging
import asyncio
import smtplib
from datetime import datetime
from email.message import EmailMessage

import httpx

from app.core.config import settings

logger = logging.getLogger("mailer")


def _smtp_configured() -> bool:
    return bool(
        (settings.smtp_host or "").strip()
        and (settings.smtp_username or "").strip()
        and (settings.smtp_password or "").strip()
        and (settings.smtp_from_email or "").strip()
    )


def _sendgrid_configured() -> bool:
    return bool(
        (settings.sendgrid_api_key or "").strip() and (settings.sendgrid_from_email or "").strip()
    )


def _send_via_smtp(to_email: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.smtp_from_email.strip()  # type: ignore[union-attr]
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    if settings.smtp_use_tls:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            server.starttls()
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(msg)
    else:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(msg)


async def _send_via_sendgrid(to_email: str, subject: str, body: str) -> None:
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": settings.sendgrid_from_email.strip()},  # type: ignore[union-attr]
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }
    headers = {
        "Authorization": f"Bearer {settings.sendgrid_api_key.strip()}",  # type: ignore[union-attr]
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


async def send_booking_email(user_email: str, service_name: str, appointment_time: datetime) -> None:
    """Send booking confirmation. Tries SMTP via asyncio.to_thread, then SendGrid fallback."""
    subject = "Appointment booked successfully"
    body = (
        "Your appointment has been booked.\n\n"
        f"Service: {service_name}\n"
        f"Date & Time: {_fmt_dt(appointment_time)}\n\n"
        "If this was not you, please contact support."
    )
    try:
        if _smtp_configured():
            await asyncio.to_thread(_send_via_smtp, user_email, subject, body)
            return
        if _sendgrid_configured():
            await _send_via_sendgrid(user_email, subject, body)
            return
        logger.info("Neither SMTP nor SendGrid configured; skipping booking email")
    except Exception:
        logger.exception("Failed to send booking email")


async def send_cancellation_email(
    user_email: str, service_name: str, appointment_time: datetime
) -> None:
    """Send cancellation confirmation. Tries SMTP via asyncio.to_thread, then SendGrid fallback."""
    subject = "Appointment cancelled"
    body = (
        "Your appointment has been cancelled.\n\n"
        f"Service: {service_name}\n"
        f"Date & Time: {_fmt_dt(appointment_time)}\n\n"
        "If this was not you, please contact support."
    )
    try:
        if _smtp_configured():
            await asyncio.to_thread(_send_via_smtp, user_email, subject, body)
            return
        if _sendgrid_configured():
            await _send_via_sendgrid(user_email, subject, body)
            return
        logger.info("Neither SMTP nor SendGrid configured; skipping cancellation email")
    except Exception:
        logger.exception("Failed to send cancellation email")

