from datetime import time
from decimal import Decimal

from pydantic import BaseModel, Field


class ServiceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slot_duration_minutes: int = Field(description="Allowed values: 15, 30, 60")
    slot_start_time: time
    slot_end_time: time
    price: Decimal = Field(gt=0)


class ServiceOut(BaseModel):
    id: int
    name: str
    slot_duration_minutes: int
    slot_start_time: time
    slot_end_time: time
    price: Decimal

    class Config:
        from_attributes = True
