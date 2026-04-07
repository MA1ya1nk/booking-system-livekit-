from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.service import ServiceOut


class AppointmentCreate(BaseModel):
    service_id: int
    appointment_time: datetime = Field(description="Use local datetime, e.g. 2026-04-08T10:30:00")
    note: str | None = Field(default=None, max_length=500)


class AppointmentOut(BaseModel):
    id: int
    appointment_time: datetime
    note: str | None
    status: str
    service: ServiceOut

    class Config:
        from_attributes = True
