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
