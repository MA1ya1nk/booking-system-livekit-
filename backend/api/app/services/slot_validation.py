"""Shared validation for appointment time vs service slot rules."""

from datetime import datetime

from fastapi import HTTPException, status

from app.models.service import Service


def validate_appointment_slot(service: Service, appointment_time: datetime) -> None:
    """Raises HTTPException if the time does not align with the service window and duration."""
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


def validate_future_appointment(appointment_time: datetime) -> None:
    if appointment_time <= datetime.now():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use a future date and time",
        )


def slot_validation_error_message(service: Service, appointment_time: datetime) -> str | None:
    """Returns a human-readable reason if the slot is invalid, or None if slot rules pass (ignores DB conflicts)."""
    if appointment_time <= datetime.now():
        return "Use a future date and time"
    try:
        validate_appointment_slot(service, appointment_time)
    except HTTPException as e:
        detail = e.detail
        return detail if isinstance(detail, str) else "Invalid appointment time"
    return None
