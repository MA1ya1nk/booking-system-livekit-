from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import time

from app.db.base import Base


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    slot_duration_minutes: Mapped[int] = mapped_column(nullable=False)
    slot_start_time: Mapped[time] = mapped_column(Time, nullable=False)
    slot_end_time: Mapped[time] = mapped_column(Time, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    appointments = relationship("Appointment", back_populates="service", cascade="all, delete-orphan")
