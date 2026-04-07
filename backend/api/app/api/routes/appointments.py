from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.appointment import Appointment, AppointmentStatus
from app.models.service import Service
from app.models.user import User
from app.schemas.appointment import AppointmentCreate, AppointmentOut

router = APIRouter(prefix="/appointments", tags=["appointments"])


def _validate_slot(service: Service, appointment_time: datetime) -> None:
    minute = appointment_time.minute
    if minute % service.slot_duration_minutes != 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Minute must align with slot duration {service.slot_duration_minutes}",
        )
    if appointment_time.time() < service.slot_start_time or appointment_time.time() >= service.slot_end_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Appointment time outside service slot range",
        )


@router.post("", response_model=AppointmentOut)
def create_appointment(
    payload: AppointmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = db.get(Service, payload.service_id)
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    if payload.appointment_time <= datetime.now():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use a future date/time")

    _validate_slot(service, payload.appointment_time)

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
        user_id=current_user.id,
        service_id=payload.service_id,
        appointment_time=payload.appointment_time,
        note=payload.note,
        status=AppointmentStatus.BOOKED,
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    return appointment


@router.get("/me", response_model=list[AppointmentOut])
def my_appointments(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = db.scalars(
        select(Appointment)
        .options(joinedload(Appointment.service))
        .where(Appointment.user_id == current_user.id)
        .order_by(Appointment.appointment_time.desc())
    ).all()
    return list(rows)


@router.get("/booked-slots")
def booked_slots(
    service_id: int,
    day: date,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
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


@router.patch("/{appointment_id}/cancel", response_model=AppointmentOut)
def cancel_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    appointment = db.get(Appointment, appointment_id)
    if not appointment or appointment.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    appointment.status = AppointmentStatus.CANCELLED
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    return appointment
