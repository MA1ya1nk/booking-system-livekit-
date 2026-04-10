from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.core.appointment_timezone import aware_appointment_datetime_for_json, normalize_to_naive_appointment_time
from app.schemas.service import ServiceOut


class AppointmentCreate(BaseModel):
    service_id: int
    appointment_time: datetime = Field(
        description="Wall time in appointment timezone (default Asia/Kolkata), e.g. 2026-04-08T10:30:00; or ISO with offset",
    )
    note: str | None = Field(default=None, max_length=500)

    @field_validator("appointment_time")
    @classmethod
    def _normalize_appointment_time(cls, v: datetime) -> datetime:
        return normalize_to_naive_appointment_time(v)


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    appointment_time: datetime
    note: str | None
    status: str
    service: ServiceOut

    @field_serializer("appointment_time")
    def _serialize_appointment_time(self, v: datetime) -> datetime:
        return aware_appointment_datetime_for_json(v)
