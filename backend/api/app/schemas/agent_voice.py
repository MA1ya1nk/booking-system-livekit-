from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class EmailVerifyRequest(BaseModel):
    email: EmailStr


class EmailVerifyResponse(BaseModel):
    exists: bool


class VoiceAppointmentCreate(BaseModel):
    email: EmailStr
    service_id: int
    appointment_time: datetime = Field(
        description="Local naive datetime, e.g. 2026-04-08T10:30:00",
    )
    note: str | None = Field(default=None, max_length=500)


class SlotAvailableResponse(BaseModel):
    available: bool
    reason: str | None = None


class VoiceBookingListItem(BaseModel):
    appointment_id: int
    service_id: int
    service_name: str
    appointment_time: datetime


class VoiceMyAppointmentsResponse(BaseModel):
    appointments: list[VoiceBookingListItem]


class VoiceAppointmentCancelRequest(BaseModel):
    email: EmailStr
    appointment_id: int
