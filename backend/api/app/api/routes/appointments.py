import asyncio
from datetime import date, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.appointment import Appointment, AppointmentStatus
from app.models.service import Service
from app.models.user import User
from app.schemas.appointment import AppointmentOut
from app.services.mailer import send_cancellation_email

router = APIRouter(prefix="/appointments", tags=["appointments"])


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
        # Return local wall-time format without timezone suffix so frontend slot keys match exactly.
        "slots": [item.appointment_time.strftime("%Y-%m-%dT%H:%M:%S") for item in rows],
    }


@router.patch("/{appointment_id}/cancel", response_model=AppointmentOut)
def cancel_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    background_tasks: BackgroundTasks = None,
):
    appointment = db.get(Appointment, appointment_id)
    if not appointment or appointment.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    appointment.status = AppointmentStatus.CANCELLED
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    service = db.get(Service, appointment.service_id)
    if background_tasks is not None:
        background_tasks.add_task(
            asyncio.run,
            send_cancellation_email(
                user_email=current_user.email,
                service_name=service.name if service else "Hospital Service",
                appointment_time=appointment.appointment_time,
            ),
        )
    return appointment
