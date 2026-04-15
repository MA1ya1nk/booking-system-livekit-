"""Razorpay: Orders (Checkout), Payment Links (email), and webhooks."""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

import razorpay
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.appointment_timezone import aware_appointment_datetime_for_json
from app.core.config import settings
from app.db.session import get_db
from app.models.appointment import Appointment, AppointmentStatus
from app.models.service import Service
from app.models.user import User
from app.schemas.appointment import AppointmentCreate, AppointmentOut
from app.services.booking import create_booking, get_appointment_with_service
from app.services.mailer import is_mailer_configured, send_booking_email, send_payment_link_email
from app.services.slot_validation import validate_appointment_slot, validate_future_appointment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])


class RazorpayVerifyBody(BaseModel):
    razorpay_order_id: str = Field(..., min_length=1)
    razorpay_payment_id: str = Field(..., min_length=1)
    razorpay_signature: str = Field(..., min_length=1)


def _require_razorpay() -> tuple[str, str]:
    key_id = (settings.razorpay_key_id or "").strip()
    key_secret = (settings.razorpay_key_secret or "").strip()
    if not key_id or not key_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Razorpay is not configured (set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)",
        )
    return key_id, key_secret


def _client() -> razorpay.Client:
    kid, secret = _require_razorpay()
    return razorpay.Client(auth=(kid, secret))


def _inr_paise(price: Decimal) -> int:
    paise = (price * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(paise)


def _refund_if_needed(client: razorpay.Client, payment_id: str, amount: int | None) -> None:
    if not amount:
        return
    try:
        client.payment.refund(payment_id, {"amount": amount})
        logger.info("Issued Razorpay refund for payment_id=%s", payment_id)
    except razorpay.errors.BadRequestError:
        logger.exception("Razorpay refund failed for payment_id=%s", payment_id)


def _merge_notes(*parts: dict | None) -> dict:
    """Later dicts override earlier; skip empty values."""
    out: dict = {}
    for p in parts:
        if not p:
            continue
        for k, v in p.items():
            if v is None:
                continue
            if isinstance(v, str) and not v.strip():
                continue
            out[str(k)] = v
    return out


def _notes_have_booking_fields(notes: dict) -> bool:
    return bool(
        notes.get("user_id") is not None
        and str(notes.get("user_id", "")).strip() not in ("", "0")
        and notes.get("service_id") is not None
        and str(notes.get("service_id", "")).strip() not in ("", "0")
        and notes.get("appointment_time")
    )


def _parse_note_appointment_time(raw: str) -> datetime:
    s = (raw or "").strip()
    if not s:
        raise ValueError("appointment_time empty")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _resolve_payment_link_booking_notes(
    client: razorpay.Client,
    pl_entity: dict,
    pay_entity: dict,
    payment_id: str,
) -> dict:
    """
    Razorpay sometimes omits custom notes on the webhook's payment_link.entity only.
    Merge payment_link + payment notes, then fall back to payment.fetch / payment_link.fetch.
    """
    notes = _merge_notes(pl_entity.get("notes"), pay_entity.get("notes"))
    if _notes_have_booking_fields(notes):
        return notes
    try:
        pay_full = client.payment.fetch(payment_id)
        notes = _merge_notes(notes, pay_full.get("notes"))
    except razorpay.errors.BadRequestError:
        logger.exception("Webhook: payment.fetch failed for %s", payment_id)
    if _notes_have_booking_fields(notes):
        return notes
    pl_id = pl_entity.get("id")
    if pl_id:
        try:
            pl_full = client.payment_link.fetch(pl_id)
            notes = _merge_notes(notes, pl_full.get("notes"))
        except razorpay.errors.BadRequestError:
            logger.exception("Webhook: payment_link.fetch failed for %s", pl_id)
    return notes


def _enqueue_booking_confirmation_email(
    background_tasks: BackgroundTasks,
    *,
    user_email: str,
    service_name: str,
    appointment_time: datetime,
) -> None:
    async def _send() -> None:
        await send_booking_email(
            user_email=user_email,
            service_name=service_name,
            appointment_time=appointment_time,
        )

    def _run_sync() -> None:
        asyncio.run(_send())

    background_tasks.add_task(_run_sync)


def _validate_booking_request(
    db: Session,
    user: User,
    payload: AppointmentCreate,
) -> tuple[Service, int, str, str]:
    """
    Returns (service, amount_paise, appointment_time_iso, note_for_notes).
    Raises HTTPException if slot invalid or taken.
    """
    service = db.get(Service, payload.service_id)
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

    validate_future_appointment(payload.appointment_time)
    validate_appointment_slot(service, payload.appointment_time)

    already_booked = db.scalar(
        select(Appointment).where(
            and_(
                Appointment.service_id == payload.service_id,
                Appointment.appointment_time == payload.appointment_time,
                Appointment.status == AppointmentStatus.BOOKED,
            )
        )
    )
    if already_booked:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slot already booked")

    amount = _inr_paise(service.price)
    if amount < 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Service price must be at least ₹1.00 for Razorpay",
        )

    time_str = payload.appointment_time.isoformat(timespec="seconds")
    note_str = (payload.note or "")[:500]
    return service, amount, time_str, note_str


async def create_payment_link_for_user_email(
    db: Session,
    user: User,
    payload: AppointmentCreate,
    *,
    expire_in_seconds: int | None = None,
) -> dict:
    """
    Create a Razorpay Payment Link with booking notes; webhook creates the appointment after payment.
    If expire_in_seconds is set, Razorpay expires the link after that window (e.g. 300 = 5 minutes).
    """
    _require_razorpay()
    service, amount, time_str, note_str = _validate_booking_request(db, user, payload)

    ref = f"ref_{uuid.uuid4().hex[:20]}"[:40]
    client = _client()
    pl_body: dict = {
        "amount": amount,
        "currency": "INR",
        "accept_partial": False,
        "description": f"Appointment: {service.name}",
        "reference_id": ref,
        "customer": {
            "email": user.email,
            "name": (user.name or user.email.split("@")[0])[:120],
        },
        "notify": {"sms": False, "email": False},
        "reminder_enable": True,
        "notes": {
            "user_id": str(user.id),
            "service_id": str(payload.service_id),
            "appointment_time": time_str,
            "note": note_str,
        },
    }
    if expire_in_seconds is not None:
        pl_body["expire_by"] = int(time.time()) + int(expire_in_seconds)

    try:
        pl = client.payment_link.create(pl_body)
    except razorpay.errors.BadRequestError as e:
        logger.exception("Razorpay payment link create failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e) or "Razorpay payment link failed",
        ) from e

    short_url = pl.get("short_url")
    if not short_url:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Razorpay returned no payment link URL")

    adt = aware_appointment_datetime_for_json(payload.appointment_time)
    summary = adt.strftime("%Y-%m-%d %H:%M %Z")
    amount_rupees = str(service.price.quantize(Decimal("0.01")))

    pay_within_minutes: int | None = None
    if expire_in_seconds is not None:
        pay_within_minutes = max(1, (int(expire_in_seconds) + 59) // 60)

    email_sent = False
    if is_mailer_configured():
        await send_payment_link_email(
            user_email=user.email,
            service_name=service.name,
            amount_rupees=amount_rupees,
            appointment_summary=summary,
            pay_url=short_url,
            pay_within_minutes=pay_within_minutes,
        )
        email_sent = True

    out: dict = {
        "sent": True,
        "email_sent": email_sent,
        "payment_link_id": pl.get("id"),
        "short_url": short_url,
    }
    if expire_in_seconds is not None:
        out["expires_in_seconds"] = int(expire_in_seconds)
    return out


@router.post("/create-order")
def create_booking_order(
    payload: AppointmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Validate slot and create a Razorpay order. Frontend opens Checkout with returned key_id + order_id."""
    kid, _ = _require_razorpay()
    service, amount, time_str, note_str = _validate_booking_request(db, current_user, payload)

    receipt = f"r_{uuid.uuid4().hex[:16]}"[:40]
    client = _client()
    try:
        order = client.order.create(
            {
                "amount": amount,
                "currency": "INR",
                "receipt": receipt,
                "notes": {
                    "user_id": str(current_user.id),
                    "service_id": str(payload.service_id),
                    "appointment_time": time_str,
                    "note": note_str,
                },
            }
        )
    except razorpay.errors.BadRequestError as e:
        logger.exception("Razorpay order create failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e) or "Razorpay order failed",
        ) from e

    return {
        "order_id": order["id"],
        "amount": amount,
        "currency": "INR",
        "key_id": kid,
    }


@router.post("/send-payment-link-email")
async def send_booking_payment_link_email(
    payload: AppointmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a Razorpay Payment Link and email it to the logged-in user.
    After they pay, webhook payment_link.paid creates the booking and sends the usual confirmation email.
    """
    return await create_payment_link_for_user_email(
        db, current_user, payload, expire_in_seconds=None
    )


@router.post("/verify-and-book", response_model=AppointmentOut)
def verify_payment_and_book(
    body: RazorpayVerifyBody,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verify Razorpay signature, then create the booking. Refunds if booking cannot be completed."""
    client = _client()

    params_dict = {
        "razorpay_order_id": body.razorpay_order_id,
        "razorpay_payment_id": body.razorpay_payment_id,
        "razorpay_signature": body.razorpay_signature,
    }
    try:
        client.utility.verify_payment_signature(params_dict)
    except razorpay.errors.SignatureVerificationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payment signature",
        ) from e

    try:
        order = client.order.fetch(body.razorpay_order_id)
        payment = client.payment.fetch(body.razorpay_payment_id)
    except razorpay.errors.BadRequestError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    if payment.get("order_id") != body.razorpay_order_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment does not match order")

    if payment.get("status") not in ("captured", "authorized"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payment not successful (status={payment.get('status')})",
        )

    notes = order.get("notes") or {}
    pay_amount = int(payment.get("amount") or 0)
    try:
        user_id = int(notes.get("user_id", 0))
        service_id = int(notes.get("service_id", 0))
        appointment_time = datetime.fromisoformat(notes["appointment_time"])
        note_raw = notes.get("note") or ""
        note = note_raw.strip() or None
    except (KeyError, ValueError, TypeError) as e:
        _refund_if_needed(client, body.razorpay_payment_id, pay_amount)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid order notes") from e

    if user_id != current_user.id:
        _refund_if_needed(client, body.razorpay_payment_id, pay_amount)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Order does not belong to this user")

    if pay_amount != int(order.get("amount") or 0):
        _refund_if_needed(client, body.razorpay_payment_id, pay_amount)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Amount mismatch")

    try:
        appointment = create_booking(
            db,
            user_id=user_id,
            service_id=service_id,
            appointment_time=appointment_time,
            note=note,
        )
    except HTTPException as e:
        db.rollback()
        if e.status_code == status.HTTP_409_CONFLICT:
            row = db.scalar(
                select(Appointment).where(
                    and_(
                        Appointment.service_id == service_id,
                        Appointment.appointment_time == appointment_time,
                        Appointment.status == AppointmentStatus.BOOKED,
                    )
                )
            )
            if row and row.user_id == user_id:
                appt = get_appointment_with_service(db, row.id)
                if appt:
                    return appt
        _refund_if_needed(client, body.razorpay_payment_id, pay_amount)
        raise

    appt = get_appointment_with_service(db, appointment.id)
    if appt and appt.service:
        _enqueue_booking_confirmation_email(
            background_tasks,
            user_email=current_user.email,
            service_name=appt.service.name,
            appointment_time=appt.appointment_time,
        )

    if not appt:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Booking created but could not load")
    return appt


def _finalize_booking_from_webhook_notes(
    db: Session,
    client: razorpay.Client,
    payment_id: str,
    pay_amount: int,
    notes: dict,
    background_tasks: BackgroundTasks,
) -> None:
    """Create booking from webhook notes; refund on failure."""
    try:
        user_id = int(notes.get("user_id", 0))
        service_id = int(notes.get("service_id", 0))
        appointment_time = _parse_note_appointment_time(str(notes["appointment_time"]))
        note_raw = notes.get("note") or ""
        note = note_raw.strip() or None
    except (KeyError, ValueError, TypeError) as e:
        _refund_if_needed(client, payment_id, pay_amount)
        logger.warning("Webhook: invalid notes %s: %s", notes, e)
        return

    try:
        appointment = create_booking(
            db,
            user_id=user_id,
            service_id=service_id,
            appointment_time=appointment_time,
            note=note,
        )
    except HTTPException as e:
        db.rollback()
        if e.status_code == status.HTTP_409_CONFLICT:
            row = db.scalar(
                select(Appointment).where(
                    and_(
                        Appointment.service_id == service_id,
                        Appointment.appointment_time == appointment_time,
                        Appointment.status == AppointmentStatus.BOOKED,
                    )
                )
            )
            if row and row.user_id == user_id:
                logger.info("Webhook idempotent: booking already exists")
                return
        _refund_if_needed(client, payment_id, pay_amount)
        logger.warning("Webhook booking failed: %s", e.detail)
        return

    user = db.get(User, user_id)
    appt = get_appointment_with_service(db, appointment.id)
    if appt and appt.service and user:
        _enqueue_booking_confirmation_email(
            background_tasks,
            user_email=user.email,
            service_name=appt.service.name,
            appointment_time=appt.appointment_time,
        )


def _handle_payment_link_paid_webhook(
    data: dict,
    db: Session,
    client: razorpay.Client,
    background_tasks: BackgroundTasks,
) -> dict:
    payload = data.get("payload") or {}
    pl_wrap = payload.get("payment_link") or {}
    pay_wrap = payload.get("payment") or {}
    pl_entity = pl_wrap.get("entity") or {}
    pay_entity = pay_wrap.get("entity") or {}

    payment_id = pay_entity.get("id")
    pay_amount = int(pay_entity.get("amount") or 0)
    pl_amount = int(pl_entity.get("amount") or 0)

    if not payment_id:
        logger.warning("Webhook payment_link.paid: missing payment id")
        return {"ok": True}

    if pay_entity.get("status") not in ("captured", "authorized"):
        logger.warning("Webhook: payment status %s", pay_entity.get("status"))
        return {"ok": True}

    if pl_amount and pay_amount and pl_amount != pay_amount:
        _refund_if_needed(client, payment_id, pay_amount)
        logger.warning("Webhook: amount mismatch pl=%s pay=%s", pl_amount, pay_amount)
        return {"ok": True}

    notes = _resolve_payment_link_booking_notes(client, pl_entity, pay_entity, payment_id)
    if not _notes_have_booking_fields(notes):
        _refund_if_needed(client, payment_id, pay_amount)
        logger.warning(
            "Webhook payment_link.paid: booking notes missing after merge/fetch; raw_pl_notes=%s raw_pay_notes=%s",
            pl_entity.get("notes"),
            pay_entity.get("notes"),
        )
        return {"ok": True}

    _finalize_booking_from_webhook_notes(
        db, client, payment_id, pay_amount, notes, background_tasks
    )
    return {"ok": True}


def _handle_payment_captured_for_booking(
    data: dict,
    db: Session,
    client: razorpay.Client,
    background_tasks: BackgroundTasks,
) -> dict:
    """
    Fallback when Razorpay delivers payment.captured (e.g. extra active event) but not payment_link.paid.
    Only creates a booking when payment notes match our payment-link shape (user_id, service_id, appointment_time).
    """
    payload = data.get("payload") or {}
    pay_wrap = payload.get("payment") or {}
    pay_entity = pay_wrap.get("entity") or {}
    payment_id = pay_entity.get("id")
    pay_amount = int(pay_entity.get("amount") or 0)

    if not payment_id or pay_entity.get("status") != "captured":
        return {"ok": True, "ignored": "payment.captured_incomplete"}

    notes = _merge_notes(pay_entity.get("notes"))
    if not _notes_have_booking_fields(notes):
        try:
            pay_full = client.payment.fetch(payment_id)
            notes = _merge_notes(notes, pay_full.get("notes"))
        except razorpay.errors.BadRequestError:
            logger.exception("Webhook payment.captured: payment.fetch failed for %s", payment_id)

    if not _notes_have_booking_fields(notes):
        return {"ok": True, "ignored": "payment.captured_no_booking_notes"}

    _finalize_booking_from_webhook_notes(
        db, client, payment_id, pay_amount, notes, background_tasks
    )
    return {"ok": True}


@router.post("/webhook")
async def razorpay_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Razorpay webhooks: payment_link.paid (primary) and payment.captured (fallback) to create booking.
    Configure in Dashboard: URL .../api/v1/payments/webhook — secret: RAZORPAY_WEBHOOK_SECRET
    """
    wh_secret = (settings.razorpay_webhook_secret or "").strip()
    if not wh_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAZORPAY_WEBHOOK_SECRET not set",
        )

    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8")
    sig = request.headers.get("X-Razorpay-Signature")
    if not sig:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing X-Razorpay-Signature")

    client = _client()
    try:
        client.utility.verify_webhook_signature(body_str, sig, wh_secret)
    except razorpay.errors.SignatureVerificationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature") from e

    try:
        data = json.loads(body_str)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON") from e

    event = data.get("event")
    if event == "payment_link.paid":
        return _handle_payment_link_paid_webhook(data, db, client, background_tasks)
    if event == "payment.captured":
        return _handle_payment_captured_for_booking(data, db, client, background_tasks)
    return {"ok": True, "ignored": event}
