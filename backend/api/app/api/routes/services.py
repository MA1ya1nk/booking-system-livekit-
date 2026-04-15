from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models.service import Service
from app.models.user import User
from app.schemas.service import ServiceCreate, ServiceOut
from app.services.appointment_commit import _is_unique_violation

router = APIRouter(prefix="/services", tags=["services"])


@router.get("", response_model=list[ServiceOut])
def list_services(db: Session = Depends(get_db)):
    return list(db.scalars(select(Service).order_by(Service.name)).all())


@router.post("", response_model=ServiceOut)
def create_service(
    payload: ServiceCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if payload.slot_duration_minutes not in [15, 30, 60]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="slot_duration_minutes must be 15, 30 or 60",
        )

    if payload.slot_start_time >= payload.slot_end_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="slot_start_time must be before slot_end_time",
        )

    service = Service(
        name=payload.name.strip(),
        slot_duration_minutes=payload.slot_duration_minutes,
        slot_start_time=payload.slot_start_time,
        slot_end_time=payload.slot_end_time,
        price=payload.price,
        created_by_user_id=admin.id,
    )
    db.add(service)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if _is_unique_violation(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A service with this name already exists",
            ) from None
        raise
    db.refresh(service)
    return service
