from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin_or_supervisor
from app.db.session import get_db
from app.models.tables import Client, Shift, ClientShiftSlot
from app.services.paycalc_service import compute_shift_calc

router = APIRouter()

# ---- Schemas ----
class ClientCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    active: Optional[int] = 1
    bill_day: Optional[float] = None
    bill_night: Optional[float] = None
    day_window_start: Optional[str] = "07:00"
    day_window_end: Optional[str] = "23:00"
    # legacy aliases
    rate_day: Optional[float] = None
    rate_night: Optional[float] = None

    # NEW
    invoice_cycle: Optional[str] = "WEEKLY"
    invoice_anchor_dow: Optional[int] = 6
    invoice_anchor_time: Optional[str] = "23:00"
    timezone: Optional[str] = None

    holiday_bill_multiplier: Optional[float] = None
    holiday_pay_multiplier: Optional[float] = None

class ClientUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    active: Optional[int] = None
    bill_day: Optional[float] = None
    bill_night: Optional[float] = None
    day_window_start: Optional[str] = None
    day_window_end: Optional[str] = None
    rate_day: Optional[float] = None
    rate_night: Optional[float] = None

    # NEW
    invoice_cycle: Optional[str] = None
    invoice_anchor_dow: Optional[int] = None
    invoice_anchor_time: Optional[str] = None
    timezone: Optional[str] = None
    
    holiday_bill_multiplier: Optional[float] = None
    holiday_pay_multiplier: Optional[float] = None

def _serialize_client(c: Client) -> Dict:
    return {
        "client_id": c.client_id,
        "name": c.name,
        "email": c.email,
        "phone": c.phone,
        "address": c.address,
        "active": c.active,
        "bill_day": c.bill_day,
        "bill_night": c.bill_night,
        "day_window_start": c.day_window_start,
        "day_window_end": c.day_window_end,
        # NEW
        "invoice_cycle": c.invoice_cycle,
        "invoice_anchor_dow": c.invoice_anchor_dow,
        "invoice_anchor_time": c.invoice_anchor_time,
        "timezone": c.timezone,
        "holiday_bill_multiplier": c.holiday_bill_multiplier,
        "holiday_pay_multiplier":  c.holiday_pay_multiplier,
    }

def _validate_cycle_fields(invoice_cycle, invoice_anchor_dow, invoice_anchor_time):
    if invoice_cycle and invoice_cycle.upper() not in ("WEEKLY",):
        raise HTTPException(status_code=400, detail="invoice_cycle must be WEEKLY")
    if invoice_anchor_dow is not None and not (0 <= int(invoice_anchor_dow) <= 6):
        raise HTTPException(status_code=400, detail="invoice_anchor_dow must be 0..6 (Mon..Sun)")
    if invoice_anchor_time:
        parts = str(invoice_anchor_time).split(":")
        if len(parts) != 2:
            raise HTTPException(status_code=400, detail="invoice_anchor_time must be HH:MM")
        hh, mm = parts
        if not (hh.isdigit() and mm.isdigit() and 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
            raise HTTPException(status_code=400, detail="invoice_anchor_time must be HH:MM")

def _validate_hhmm(value: str | None, field_name: str) -> None:
    if value is None:
        return
    parts = str(value).split(":")
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail=f"{field_name} must be HH:MM")
    hh, mm = parts
    if not (hh.isdigit() and mm.isdigit() and 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
        raise HTTPException(status_code=400, detail=f"{field_name} must be HH:MM")

def _validate_non_negative(value: float | None, field_name: str) -> None:
    if value is not None and value < 0:
        raise HTTPException(status_code=400, detail=f"{field_name} cannot be negative")

# ---- Shift-slot helpers ----

_DEFAULT_SLOTS = [
    ("Morning",   "07:00", "15:00", "DAY",   0),
    ("Afternoon", "15:00", "23:00", "DAY",   1),
    ("Night",     "23:00", "07:00", "NIGHT", 2),
]

def _seed_default_slots(db: Session, client_id: int) -> None:
    for name, st, et, rt, so in _DEFAULT_SLOTS:
        db.add(ClientShiftSlot(
            client_id=client_id, slot_name=name,
            start_time=st, end_time=et,
            rate_type=rt, sort_order=so
        ))

def _serialize_slot(s: ClientShiftSlot) -> Dict:
    return {
        "slot_id": s.slot_id,
        "client_id": s.client_id,
        "slot_name": s.slot_name,
        "start_time": s.start_time,
        "end_time": s.end_time,
        "rate_type": s.rate_type,
        "sort_order": s.sort_order,
    }

def _recalculate_closed_shifts_for_client(db: Session, client_id: int) -> None:
    closed_shift_ids = (
        db.query(Shift.shift_id)
        .filter(Shift.client_id == client_id)
        .filter(Shift.status == "CLOSED")
        .filter(Shift.check_in_ts.isnot(None), Shift.check_out_ts.isnot(None))
        .all()
    )
    for (shift_id,) in closed_shift_ids:
        compute_shift_calc(db, shift_id)


# ---- Endpoints ----

@router.get("/clients", response_model=List[Dict])
def list_clients(
    _: object = Depends(require_admin_or_supervisor),
    db: Session = Depends(get_db),
):
    rows = db.query(Client).order_by(Client.client_id.asc()).all()
    return [_serialize_client(c) for c in rows]

@router.get("/clients/{client_id}", response_model=Dict)
def get_client(
    client_id: int = Path(...),
    _: object = Depends(require_admin_or_supervisor),
    db: Session = Depends(get_db),
):
    c = db.query(Client).filter(Client.client_id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    return _serialize_client(c)

@router.post("/clients")
def create_client(payload: ClientCreate,
                  db: Session = Depends(get_db),
                  _: object = Depends(require_admin_or_supervisor)):
    # validate cycle inputs
    _validate_cycle_fields(payload.invoice_cycle, payload.invoice_anchor_dow, payload.invoice_anchor_time)
    _validate_hhmm(payload.day_window_start, "day_window_start")
    _validate_hhmm(payload.day_window_end, "day_window_end")
    _validate_non_negative(payload.bill_day, "bill_day")
    _validate_non_negative(payload.bill_night, "bill_night")

    c = Client(
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        address=payload.address,
        active=payload.active if payload.active is not None else 1,

        # billing rates: prefer explicit bill_* else accept legacy names
        bill_day=(payload.bill_day if payload.bill_day is not None else payload.rate_day),
        bill_night=(payload.bill_night if payload.bill_night is not None else payload.rate_night),
        day_window_start=payload.day_window_start,
        day_window_end=payload.day_window_end,

        # invoice cycle
        invoice_cycle=(payload.invoice_cycle or "WEEKLY"),
        invoice_anchor_dow=(payload.invoice_anchor_dow if payload.invoice_anchor_dow is not None else 6),
        invoice_anchor_time=(payload.invoice_anchor_time or "23:00"),
        timezone=payload.timezone,  # can be None → service layer defaults to settings

        # holiday multipliers
        holiday_bill_multiplier=payload.holiday_bill_multiplier,
        holiday_pay_multiplier=payload.holiday_pay_multiplier,
    )

    db.add(c)
    db.flush()
    _seed_default_slots(db, c.client_id)
    db.commit()
    db.refresh(c)

    return {
        "client_id": c.client_id,
        "name": c.name,
        "email": c.email,
        "phone": c.phone,
        "address": c.address,
        "active": c.active,
        "bill_day": c.bill_day,
        "bill_night": c.bill_night,
        "day_window_start": c.day_window_start,
        "day_window_end": c.day_window_end,
        "invoice_cycle": c.invoice_cycle,
        "invoice_anchor_dow": c.invoice_anchor_dow,
        "invoice_anchor_time": c.invoice_anchor_time,
        "timezone": c.timezone,
        "holiday_bill_multiplier": c.holiday_bill_multiplier,
        "holiday_pay_multiplier": c.holiday_pay_multiplier,
    }


@router.put("/clients/{client_id}")
def update_client(client_id: int,
                  payload: ClientUpdate,
                  db: Session = Depends(get_db),
                  _: object = Depends(require_admin_or_supervisor)):
    c = db.query(Client).filter(Client.client_id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")

    _validate_cycle_fields(payload.invoice_cycle, payload.invoice_anchor_dow, payload.invoice_anchor_time)
    _validate_hhmm(payload.day_window_start, "day_window_start")
    _validate_hhmm(payload.day_window_end, "day_window_end")
    _validate_non_negative(payload.bill_day, "bill_day")
    _validate_non_negative(payload.bill_night, "bill_night")

    recalc_closed_shifts = any([
        payload.day_window_start is not None,
        payload.day_window_end is not None,
        payload.timezone is not None,
    ])

    if payload.name is not None: c.name = payload.name
    if payload.email is not None: c.email = payload.email
    if payload.phone is not None: c.phone = payload.phone
    if payload.address is not None: c.address = payload.address
    if payload.active is not None: c.active = payload.active

    # billing rates (prefer bill_*; accept legacy if provided)
    if payload.bill_day is not None: c.bill_day = payload.bill_day
    if payload.bill_night is not None: c.bill_night = payload.bill_night
    if payload.rate_day is not None and c.bill_day is None: c.bill_day = payload.rate_day
    if payload.rate_night is not None and c.bill_night is None: c.bill_night = payload.rate_night
    if payload.day_window_start is not None: c.day_window_start = payload.day_window_start
    if payload.day_window_end is not None: c.day_window_end = payload.day_window_end

    # invoice cycle settings
    if payload.invoice_cycle is not None: c.invoice_cycle = payload.invoice_cycle
    if payload.invoice_anchor_dow is not None: c.invoice_anchor_dow = payload.invoice_anchor_dow
    if payload.invoice_anchor_time is not None: c.invoice_anchor_time = payload.invoice_anchor_time
    if payload.timezone is not None: c.timezone = payload.timezone

    # holiday multipliers
    if payload.holiday_bill_multiplier is not None: c.holiday_bill_multiplier = payload.holiday_bill_multiplier
    if payload.holiday_pay_multiplier is not None:  c.holiday_pay_multiplier  = payload.holiday_pay_multiplier

    db.add(c)
    db.flush()
    if recalc_closed_shifts:
        _recalculate_closed_shifts_for_client(db, c.client_id)
    db.commit()
    db.refresh(c)

    return {
        "client_id": c.client_id,
        "name": c.name,
        "email": c.email,
        "phone": c.phone,
        "address": c.address,
        "active": c.active,
        "bill_day": c.bill_day,
        "bill_night": c.bill_night,
        "day_window_start": c.day_window_start,
        "day_window_end": c.day_window_end,
        "invoice_cycle": c.invoice_cycle,
        "invoice_anchor_dow": c.invoice_anchor_dow,
        "invoice_anchor_time": c.invoice_anchor_time,
        "timezone": c.timezone,
        "holiday_bill_multiplier": c.holiday_bill_multiplier,
        "holiday_pay_multiplier": c.holiday_pay_multiplier,
    }


@router.delete("/clients/{client_id}", status_code=204)
def delete_client(
    client_id: int,
    _: object = Depends(require_admin_or_supervisor),
    db: Session = Depends(get_db),
):
    from app.models.tables import Shift, PayRule
    c = db.query(Client).filter(Client.client_id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")

    any_shifts = db.query(Shift.shift_id).filter(
        Shift.client_id == client_id
    ).first()
    if any_shifts:
        open_count = db.query(Shift.shift_id).filter(
            Shift.client_id == client_id,
            Shift.status == "OPEN"
        ).count()
        if open_count:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete client '{c.name}' — they have {open_count} open shift(s). "
                       "Close or void those shifts first, then deactivate instead of deleting."
            )
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete client '{c.name}' — they have shift history on record. "
                   "Deactivate them instead (set Active = No) to preserve payroll records."
        )

    db.query(PayRule).filter(PayRule.client_id == client_id).delete()
    db.delete(c)
    db.commit()
    return


# ---- Shift-slot schemas ----

class ShiftSlotCreate(BaseModel):
    slot_name: str
    start_time: str
    end_time: str
    rate_type: str = "DAY"   # DAY | NIGHT
    sort_order: Optional[int] = 0

class ShiftSlotUpdate(BaseModel):
    slot_name: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    rate_type: Optional[str] = None
    sort_order: Optional[int] = None


# ---- Shift-slot endpoints ----

@router.get("/clients/{client_id}/shift-slots", response_model=List[Dict])
def list_shift_slots(
    client_id: int = Path(...),
    _: object = Depends(require_admin_or_supervisor),
    db: Session = Depends(get_db),
):
    c = db.query(Client).filter(Client.client_id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    slots = db.query(ClientShiftSlot).filter(
        ClientShiftSlot.client_id == client_id
    ).order_by(ClientShiftSlot.sort_order).all()
    return [_serialize_slot(s) for s in slots]


@router.post("/clients/{client_id}/shift-slots", status_code=201)
def create_shift_slot(
    client_id: int = Path(...),
    payload: ShiftSlotCreate = ...,
    _: object = Depends(require_admin_or_supervisor),
    db: Session = Depends(get_db),
):
    c = db.query(Client).filter(Client.client_id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    _validate_hhmm(payload.start_time, "start_time")
    _validate_hhmm(payload.end_time, "end_time")
    if payload.rate_type.upper() not in ("DAY", "NIGHT"):
        raise HTTPException(status_code=400, detail="rate_type must be DAY or NIGHT")
    s = ClientShiftSlot(
        client_id=client_id,
        slot_name=payload.slot_name,
        start_time=payload.start_time,
        end_time=payload.end_time,
        rate_type=payload.rate_type.upper(),
        sort_order=payload.sort_order or 0,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return _serialize_slot(s)


@router.put("/clients/{client_id}/shift-slots/{slot_id}")
def update_shift_slot(
    client_id: int = Path(...),
    slot_id: int = Path(...),
    payload: ShiftSlotUpdate = ...,
    _: object = Depends(require_admin_or_supervisor),
    db: Session = Depends(get_db),
):
    s = db.query(ClientShiftSlot).filter(
        ClientShiftSlot.slot_id == slot_id,
        ClientShiftSlot.client_id == client_id,
    ).first()
    if not s:
        raise HTTPException(status_code=404, detail="Shift slot not found")
    if payload.start_time is not None:
        _validate_hhmm(payload.start_time, "start_time")
        s.start_time = payload.start_time
    if payload.end_time is not None:
        _validate_hhmm(payload.end_time, "end_time")
        s.end_time = payload.end_time
    if payload.rate_type is not None:
        if payload.rate_type.upper() not in ("DAY", "NIGHT"):
            raise HTTPException(status_code=400, detail="rate_type must be DAY or NIGHT")
        s.rate_type = payload.rate_type.upper()
    if payload.slot_name is not None:
        s.slot_name = payload.slot_name
    if payload.sort_order is not None:
        s.sort_order = payload.sort_order
    db.commit()
    db.refresh(s)
    return _serialize_slot(s)


@router.delete("/clients/{client_id}/shift-slots/{slot_id}", status_code=204)
def delete_shift_slot(
    client_id: int = Path(...),
    slot_id: int = Path(...),
    _: object = Depends(require_admin_or_supervisor),
    db: Session = Depends(get_db),
):
    s = db.query(ClientShiftSlot).filter(
        ClientShiftSlot.slot_id == slot_id,
        ClientShiftSlot.client_id == client_id,
    ).first()
    if not s:
        raise HTTPException(status_code=404, detail="Shift slot not found")
    db.delete(s)
    db.commit()
    return

