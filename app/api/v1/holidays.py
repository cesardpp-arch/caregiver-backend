from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin_or_supervisor
from app.db.session import get_db
from app.models.tables import Holiday

router = APIRouter()

# ---- Schemas ----

class HolidayCreate(BaseModel):
    client_id: Optional[int] = None    # NULL = global holiday
    date: str                          # "YYYY-MM-DD" (local)
    name: str
    multiplier_bill: Optional[float] = None
    multiplier_pay: Optional[float] = None


class HolidayOut(BaseModel):
    holiday_id: int
    client_id: Optional[int]
    date: str
    name: str
    multiplier_bill: Optional[float]
    multiplier_pay: Optional[float]


class HolidayUpdate(BaseModel):
    client_id: Optional[int] = -1   # -1 = sentinel "not provided"; null = global
    date: Optional[str] = None
    name: Optional[str] = None
    multiplier_bill: Optional[float] = None
    multiplier_pay: Optional[float] = None


# ---- Endpoints ----

@router.post("/holidays", response_model=Dict)
def create_holiday(
    payload: HolidayCreate,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin_or_supervisor)
):
    h = Holiday(
        client_id=payload.client_id,
        date=payload.date,
        name=payload.name,
        multiplier_bill=payload.multiplier_bill,
        multiplier_pay=payload.multiplier_pay,
    )
    db.add(h)
    db.commit()
    db.refresh(h)

    return {
        "holiday_id": h.holiday_id,
        "message": "Holiday created"
    }


@router.get("/holidays", response_model=List[HolidayOut])
def list_holidays(
    client_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: object = Depends(require_admin_or_supervisor)
):
    q = db.query(Holiday)
    if client_id is not None:
        q = q.filter(
            (Holiday.client_id == client_id) | (Holiday.client_id.is_(None))
        )

    rows = q.order_by(Holiday.date.asc()).all()
    return [
        {
            "holiday_id": r.holiday_id,
            "client_id": r.client_id,
            "date": r.date,
            "name": r.name,
            "multiplier_bill": r.multiplier_bill,
            "multiplier_pay": r.multiplier_pay
        }
        for r in rows
    ]


@router.put("/holidays/{holiday_id}", response_model=HolidayOut)
def update_holiday(
    holiday_id: int,
    payload: HolidayUpdate,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin_or_supervisor)
):
    row = db.query(Holiday).filter(Holiday.holiday_id == holiday_id).first()
    if not row:
        raise HTTPException(404, "Holiday not found")

    if payload.client_id != -1:
        # null (None) means global; a positive int means client-specific
        row.client_id = payload.client_id if payload.client_id else None
    if payload.date is not None:
        row.date = payload.date
    if payload.name is not None:
        row.name = payload.name
    if payload.multiplier_bill is not None:
        row.multiplier_bill = payload.multiplier_bill
    if payload.multiplier_pay is not None:
        row.multiplier_pay = payload.multiplier_pay

    db.commit()
    db.refresh(row)
    return {
        "holiday_id": row.holiday_id,
        "client_id": row.client_id,
        "date": row.date,
        "name": row.name,
        "multiplier_bill": row.multiplier_bill,
        "multiplier_pay": row.multiplier_pay,
    }


@router.delete("/holidays/{holiday_id}", response_model=Dict)
def delete_holiday(
    holiday_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin_or_supervisor)
):
    row = db.query(Holiday).filter(Holiday.holiday_id == holiday_id).first()
    if not row:
        raise HTTPException(404, "Holiday not found")

    db.delete(row)
    db.commit()

    return {"deleted": holiday_id}
