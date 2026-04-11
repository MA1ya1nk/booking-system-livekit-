"""Create bookings (shared by Razorpay verify flow)."""

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.orm import Session, joinedload

from app.models.appointment import Appointment, AppointmentStatus
from app.models.service import Service
from app.models.user import User
from app.services.appointment_commit import commit_or_slot_conflict
from app.services.slot_validation import validate_appointment_slot, validate_future_appointment


def create_booking(
    db: Session,
    *,
    user_id: int,
    service_id: int,
    appointment_time: datetime,
    note: str | None,
) -> Appointment:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    service = db.get(Service, service_id)
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    validate_future_appointment(appointment_time)
    validate_appointment_slot(service, appointment_time)

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
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slot already booked")

    appointment = Appointment(
        user_id=user_id,
        service_id=service_id,
        appointment_time=appointment_time,
        note=note,
        status=AppointmentStatus.BOOKED,
    )
    db.add(appointment)
    commit_or_slot_conflict(db)
    db.refresh(appointment)
    return appointment


def get_appointment_with_service(db: Session, appointment_id: int) -> Appointment | None:
    return db.scalar(
        select(Appointment)
        .options(joinedload(Appointment.service))
        .where(Appointment.id == appointment_id)
    )
