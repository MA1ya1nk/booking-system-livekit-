"""Single source of truth for appointment clock: naive datetimes = wall time in `settings.appointment_timezone`."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import settings


def get_appointment_zone() -> ZoneInfo:
    return ZoneInfo(settings.appointment_timezone)


def now_naive_in_appointment_tz() -> datetime:
    return datetime.now(get_appointment_zone()).replace(tzinfo=None)


def normalize_to_naive_appointment_time(dt: datetime) -> datetime:
    """Naive values are treated as wall time in the appointment zone; aware values convert to that zone."""
    tz = get_appointment_zone()
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(tz).replace(tzinfo=None)


def aware_appointment_datetime_for_json(dt: datetime) -> datetime:
    """Naive DB values are assumed to be in the appointment zone; used for JSON ISO output with offset."""
    tz = get_appointment_zone()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def isoformat_appointment_naive(dt: datetime) -> str:
    return aware_appointment_datetime_for_json(dt).isoformat(timespec="seconds")
