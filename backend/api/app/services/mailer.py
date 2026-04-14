import logging
import asyncio
import smtplib
from datetime import datetime
from email.message import EmailMessage

import httpx

from app.core.appointment_timezone import aware_appointment_datetime_for_json
from app.core.config import settings

logger = logging.getLogger("mailer")


def _smtp_configured() -> bool:
    return bool(
        (settings.smtp_host or "").strip()
        and (settings.smtp_username or "").strip()
        and (settings.smtp_password or "").strip()
        and (settings.smtp_from_email or "").strip()
    )


def _resend_configured() -> bool:
    return bool(
        (settings.resend_api_key or "").strip() and (settings.resend_from_email or "").strip()
    )


def _sendgrid_configured() -> bool:
    return bool(
        (settings.sendgrid_api_key or "").strip() and (settings.sendgrid_from_email or "").strip()
    )


def is_mailer_configured() -> bool:
    return _resend_configured() or _sendgrid_configured() or _smtp_configured()


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


async def _send_via_resend(to_email: str, subject: str, body: str) -> None:
    payload = {
        "from": settings.resend_from_email.strip(),  # type: ignore[union-attr]
        "to": [to_email],
        "subject": subject,
        "text": body,
    }
    headers = {
        "Authorization": f"Bearer {settings.resend_api_key.strip()}",  # type: ignore[union-attr]
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()


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


async def _dispatch_email(to_email: str, subject: str, body: str) -> bool:
    """Send via Resend (preferred), then SendGrid, then SMTP. Returns True if a provider sent."""
    if _resend_configured():
        await _send_via_resend(to_email, subject, body)
        return True
    if _sendgrid_configured():
        await _send_via_sendgrid(to_email, subject, body)
        return True
    if _smtp_configured():
        await asyncio.to_thread(_send_via_smtp, to_email, subject, body)
        return True
    return False


def _fmt_dt(dt: datetime) -> str:
    adt = aware_appointment_datetime_for_json(dt)
    return adt.strftime("%Y-%m-%d %H:%M %Z")


async def send_payment_link_email(
    user_email: str,
    service_name: str,
    amount_rupees: str,
    appointment_summary: str,
    pay_url: str,
    pay_within_minutes: int | None = None,
) -> None:
    """Email a Razorpay payment link so the user can pay later (same booking as website after payment)."""
    subject = "Complete payment for your appointment"
    deadline = (
        f"You must complete payment within {pay_within_minutes} minutes or this link will expire.\n\n"
        if pay_within_minutes
        else ""
    )
    body = (
        "Please pay using the secure link below to confirm your appointment.\n\n"
        f"{deadline}"
        f"Service: {service_name}\n"
        f"Amount: ₹{amount_rupees}\n"
        f"When: {appointment_summary}\n\n"
        f"Pay now: {pay_url}\n\n"
        "After payment succeeds, you will receive a booking confirmation email.\n"
        "If you did not request this, ignore this message."
    )
    try:
        if await _dispatch_email(user_email, subject, body):
            return
        logger.info("No email provider configured; skipping payment link email")
    except Exception:
        logger.exception("Failed to send payment link email")


async def send_booking_email(user_email: str, service_name: str, appointment_time: datetime) -> None:
    """Send booking confirmation via Resend, SendGrid, or SMTP."""
    subject = "Appointment booked successfully"
    body = (
        "Your appointment has been booked.\n\n"
        f"Service: {service_name}\n"
        f"Date & Time: {_fmt_dt(appointment_time)}\n\n"
        "If this was not you, please contact support."
    )
    try:
        if await _dispatch_email(user_email, subject, body):
            return
        logger.info("No email provider configured; skipping booking email")
    except Exception:
        logger.exception("Failed to send booking email")


async def send_cancellation_email(
    user_email: str, service_name: str, appointment_time: datetime
) -> None:
    """Send cancellation confirmation via Resend, SendGrid, or SMTP."""
    subject = "Appointment cancelled"
    body = (
        "Your appointment has been cancelled.\n\n"
        f"Service: {service_name}\n"
        f"Date & Time: {_fmt_dt(appointment_time)}\n\n"
        "If this was not you, please contact support."
    )
    try:
        if await _dispatch_email(user_email, subject, body):
            return
        logger.info("No email provider configured; skipping cancellation email")
    except Exception:
        logger.exception("Failed to send cancellation email")
