from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import verify_agent_key
from app.db.session import get_db
from app.models.appointment import Appointment, AppointmentStatus
from app.models.service import Service
from app.models.user import User
from app.schemas.agent_voice import (
    EmailVerifyRequest,
    EmailVerifyResponse,
    SlotAvailableResponse,
    VoiceAppointmentCreate,
)
from app.schemas.appointment import AppointmentOut
from app.services.slot_validation import (
    slot_validation_error_message,
    validate_future_appointment,
    validate_appointment_slot,
)

router = APIRouter(prefix="/agent", tags=["agent-voice"])


@router.post("/verify-email", response_model=EmailVerifyResponse)
def verify_email_for_voice(
    payload: EmailVerifyRequest,
    db: Session = Depends(get_db),
    _: None = Depends(verify_agent_key),
):
    normalized = payload.email.strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == normalized))
    return EmailVerifyResponse(exists=user is not None)


@router.get("/booked-slots")
def agent_booked_slots(
    service_id: int,
    day: date,
    db: Session = Depends(get_db),
    _: None = Depends(verify_agent_key),
):
    start_of_day = datetime.combine(day, datetime.min.time())
    end_of_day = datetime.combine(day, datetime.max.time())
    rows = db.scalars(
        select(Appointment).where(
            and_(
                Appointment.service_id == service_id,
                Appointment.status == AppointmentStatus.BOOKED,
                Appointment.appointment_time >= start_of_day,
                Appointment.appointment_time <= end_of_day,
            )
        )
    ).all()
    return {
        "slots": [item.appointment_time.isoformat(timespec="seconds") for item in rows],
    }


@router.get("/slot-available", response_model=SlotAvailableResponse)
def agent_slot_available(
    service_id: int,
    appointment_time: datetime,
    db: Session = Depends(get_db),
    _: None = Depends(verify_agent_key),
):
    service = db.get(Service, service_id)
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

    msg = slot_validation_error_message(service, appointment_time)
    if msg:
        return SlotAvailableResponse(available=False, reason=msg)

    already_booked = db.scalar(
        select(Appointment).where(
            and_(
                Appointment.service_id == service_id,
                Appointment.appointment_time == appointment_time,
                Appointment.status == AppointmentStatus.BOOKED,
            )
        )
    )
    if already_booked:
        return SlotAvailableResponse(available=False, reason="Slot already booked")
    return SlotAvailableResponse(available=True, reason=None)


@router.post("/appointments", response_model=AppointmentOut)
def agent_create_appointment(
    payload: VoiceAppointmentCreate,
    db: Session = Depends(get_db),
    _: None = Depends(verify_agent_key),
):
    email_norm = payload.email.strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email_norm))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No registered account with this email",
        )

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

    appointment = Appointment(
        user_id=user.id,
        service_id=payload.service_id,
        appointment_time=payload.appointment_time,
        note=payload.note,
        status=AppointmentStatus.BOOKED,
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    appointment = db.scalar(
        select(Appointment)
        .options(joinedload(Appointment.service))
        .where(Appointment.id == appointment.id)
    )
    return appointment
