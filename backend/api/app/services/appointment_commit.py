"""Commit helpers for appointment writes (race-safe slot handling)."""

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def _is_unique_violation(exc: IntegrityError) -> bool:
    orig = getattr(exc.orig, "pgcode", None)
    if orig == "23505":
        return True
    msg = str(getattr(exc.orig, "args", exc) or exc).upper()
    return "UNIQUE" in msg


def commit_or_slot_conflict(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if _is_unique_violation(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Slot already booked",
            ) from None
        raise
