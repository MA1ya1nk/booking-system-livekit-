from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_serializer, field_validator

from app.core.appointment_timezone import aware_appointment_datetime_for_json, normalize_to_naive_appointment_time


class EmailVerifyRequest(BaseModel):
    email: EmailStr


class EmailVerifyResponse(BaseModel):
    exists: bool


class VoiceAppointmentCreate(BaseModel):
    email: EmailStr
    service_id: int
    appointment_time: datetime = Field(
        description="Wall time in appointment timezone (default Asia/Kolkata), e.g. 2026-04-08T10:30:00; or ISO with offset",
    )
    note: str | None = Field(default=None, max_length=500)

    @field_validator("appointment_time")
    @classmethod
    def _normalize_appointment_time(cls, v: datetime) -> datetime:
        return normalize_to_naive_appointment_time(v)


class SlotAvailableResponse(BaseModel):
    available: bool
    reason: str | None = None


class VoiceBookingListItem(BaseModel):
    appointment_id: int
    service_id: int
    service_name: str
    appointment_time: datetime

    @field_serializer("appointment_time")
    def _serialize_appointment_time(self, v: datetime) -> datetime:
        return aware_appointment_datetime_for_json(v)


class VoiceMyAppointmentsResponse(BaseModel):
    appointments: list[VoiceBookingListItem]


class VoiceAppointmentCancelRequest(BaseModel):
    email: EmailStr
    appointment_id: int
