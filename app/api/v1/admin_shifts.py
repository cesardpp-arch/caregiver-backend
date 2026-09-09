from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError

from app.db.session import get_db
from app.models.tables import Shift, ShiftCalc, Client, PayRule, Caregiver, InvoiceItem
from app.services.time_utils import combine_local_to_utc_iso
from app.services.time_utils import local_range_to_utc_bounds
from app.services.calc_utils import split_day_night_local_tz, compute_pay
from app.core.config import settings
from app.api.dependencies import require_admin_or_supervisor
from pydantic import BaseModel

from app.services.time_utils import local_date_time_to_utc_iso
from app.services.paycalc_service import compute_shift_calc  # your existing calc
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import List


router = APIRouter()

def _get_or_create_pay_rule(db: Session, client: Client, effective_start: str) -> PayRule:
    pr = (
        db.query(PayRule)
        .filter(PayRule.client_id == client.client_id, PayRule.effective_start <= effective_start)
        .order_by(PayRule.effective_start.desc())
        .first()
    )
    if pr:
        return pr

    pr = PayRule(
        client_id=client.client_id,
        rule_name="Client Config",
        rate_day=float(client.pay_day or 0.0),
        rate_night=float(client.pay_night or 0.0),
        day_window_start=(client.day_window_start or "07:00"),
        day_window_end=(client.day_window_end or "23:00"),
        overtime_after_hours=None,
        overtime_multiplier=None,
        effective_start=effective_start,
        effective_end=None,
    )
    db.add(pr)
    db.flush()
    return pr

class AdminCreateClosedShift(BaseModel):
    client_id: int
    caregiver_id: int
    start_date: str   # "YYYY-MM-DD"
    start_time: str   # "HH:MM"
    end_date: str     # "YYYY-MM-DD"
    end_time: str     # "HH:MM"
    notes: str | None = None

class AdminCreateClosedShiftBulk(BaseModel):
    items: List[AdminCreateClosedShift]

@router.post("/admin/shifts/bulk-create-closed", response_model=dict)
def admin_bulk_create_closed(
    payload: AdminCreateClosedShiftBulk,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin_or_supervisor),
):
    created = []
    errors = []

    for idx, row in enumerate(payload.items, start=1):
        try:
            client = db.query(Client).filter(Client.client_id == row.client_id).first()
            if not client:
                raise HTTPException(status_code=404, detail=f"[{idx}] Client not found")

            cg = db.query(Caregiver).filter(Caregiver.caregiver_id == row.caregiver_id).first()
            if not cg:
                raise HTTPException(status_code=404, detail=f"[{idx}] Caregiver not found")

            tzname = client.timezone or settings.TIMEZONE

            start_utc = local_date_time_to_utc_iso(row.start_date, row.start_time, tzname)
            end_utc   = local_date_time_to_utc_iso(row.end_date, row.end_time, tzname)

            if end_utc <= start_utc:
                raise HTTPException(status_code=400, detail=f"[{idx}] End must be after start")

            s = Shift(
                client_id=row.client_id,
                caregiver_id=row.caregiver_id,
                start_date=row.start_date,
                start_time=row.start_time,
                end_date=row.end_date,
                end_time=row.end_time,
                check_in_ts=start_utc,
                check_out_ts=end_utc,
                status="CLOSED",
                notes=row.notes or "",
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
            )

            db.add(s)
            db.flush()  # get shift_id

            compute_shift_calc(db, s.shift_id)

            db.commit()
            created.append({"index": idx, "shift_id": s.shift_id})

        except Exception as e:
            db.rollback()
            errors.append({"index": idx, "error": str(e)})

    return {"created": created, "errors": errors}


def _shift_row_to_dict(s: Shift):
    calc = s.calc
    return {
        "shift_id": s.shift_id,
        "status": s.status,
        "client_id": s.client_id,
        "caregiver_id": s.caregiver_id,
        "start_date": s.start_date,
        "start_time": s.start_time,
        "end_date": s.end_date,
        "end_time": s.end_time,
        "hours_day": (calc.hours_day if calc else None),
        "hours_night": (calc.hours_night if calc else None),
        "pay_day": (calc.pay_day if calc else None),
        "pay_night": (calc.pay_night if calc else None),
        "pay_total": (calc.pay_total if calc else None),
    }



@router.get("/admin/shifts", response_model=list[dict])
def list_shifts(
        caregiver_id: int | None = Query(None),
        client_id: int | None = Query(None),
        status: str | None = Query(None, description="OPEN|CLOSED|VOID"),
        from_date: str | None = Query(None, description="YYYY-MM-DD (local start date)"),
        from_time: str | None = Query(None, description="HH:MM (local start time, default 00:00 when from_date is provided)"),
        to_date: str | None = Query(None, description="YYYY-MM-DD (local end date)"),
        to_time: str | None = Query(None, description="HH:MM (local end time, default 23:59 when to_date is provided)"),
        _: object = Depends(require_admin_or_supervisor),
        db: Session = Depends(get_db),
):
    q = db.query(Shift).outerjoin(ShiftCalc, ShiftCalc.shift_id == Shift.shift_id)
    if caregiver_id: q = q.filter(Shift.caregiver_id == caregiver_id)
    if client_id: q = q.filter(Shift.client_id == client_id)
    if status: q = q.filter(Shift.status == status)

    if from_time and not from_date:
        raise HTTPException(status_code=400, detail="from_date is required when from_time is provided")
    if to_time and not to_date:
        raise HTTPException(status_code=400, detail="to_date is required when to_time is provided")
    if (from_date and not to_date) or (to_date and not from_date):
        raise HTTPException(status_code=400, detail="Both from_date and to_date are required for range filtering")

    if from_date and to_date:
        start_local_time = from_time or "00:00"
        end_local_time = to_time or "23:59"
        try:
            start_utc, end_utc = local_range_to_utc_bounds(
                from_date,
                start_local_time,
                to_date,
                end_local_time,
                settings.TIMEZONE,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

        q = q.filter(Shift.check_in_ts >= start_utc)
        q = q.filter(Shift.check_in_ts < end_utc)

    q = q.order_by(Shift.shift_id.desc())
    rows = q.all()
    return [_shift_row_to_dict(s) for s in rows]

@router.patch("/admin/shifts/{shift_id}", response_model=dict)
def edit_shift(
        shift_id: int,
        payload: dict,
        _: object = Depends(require_admin_or_supervisor),
        db: Session = Depends(get_db),
):
    """
    Editable fields (all optional): start_date, start_time, end_date, end_time, notes
    Recalculates pay snapshot if shift is CLOSED (or if end fields are provided).
    """
    s = db.query(Shift).filter(Shift.shift_id == shift_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Shift not found")

    client = db.query(Client).filter(Client.client_id == s.client_id).first()
    if not client:
        raise HTTPException(status_code=400, detail="Client not found")
    tzname = client.timezone or settings.TIMEZONE

    # Update local fields
    start_date = payload.get("start_date", s.start_date)
    start_time = payload.get("start_time", s.start_time)
    end_date   = payload.get("end_date", s.end_date)
    end_time   = payload.get("end_time", s.end_time)
    notes      = payload.get("notes", s.notes)

    # Validate and recompute UTC timestamps from local, when present
    try:
        if start_date and start_time:
            s.start_date = start_date
            s.start_time = start_time
            s.check_in_ts = combine_local_to_utc_iso(start_date, start_time, tzname)
        if end_date and end_time:
            s.end_date = end_date
            s.end_time = end_time
            s.check_out_ts = combine_local_to_utc_iso(end_date, end_time, tzname)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Bad date/time: {e}")

    if notes is not None:
        s.notes = notes

    # Ensure chronological order if both timestamps present
    if s.check_out_ts and s.check_in_ts and s.check_out_ts <= s.check_in_ts:
        raise HTTPException(status_code=400, detail="End must be after start")

    # If we now have end fields, status should be CLOSED
    if s.end_date and s.end_time:
        s.status = "CLOSED"
    db.add(s)
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        if "overlap" in str(e.orig).lower():
            raise HTTPException(status_code=409, detail="Caregiver already has a shift during this time")
        raise HTTPException(status_code=400, detail=str(e.orig))

    # Recalculate snapshot if CLOSED and we have both timestamps
    if s.status == "CLOSED" and s.check_in_ts and s.check_out_ts:
        compute_shift_calc(db, s.shift_id)

    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        if "overlap" in str(e.orig).lower():
            raise HTTPException(status_code=409, detail="Caregiver already has a shift during this time")
        raise HTTPException(status_code=400, detail=str(e.orig))
    db.refresh(s)
    return _shift_row_to_dict(s)

@router.post("/admin/shifts/{shift_id}/void", status_code=204)
def void_shift(shift_id: int, _: object = Depends(require_admin_or_supervisor), db: Session = Depends(get_db)):
    s = db.query(Shift).filter(Shift.shift_id == shift_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Shift not found")
    if s.status == "CLOSED":
        raise HTTPException(status_code=400, detail="Shift already closed")
    s.status = "VOID"
    db.add(s)
    db.commit()
    return


@router.delete("/admin/shifts/{shift_id}", status_code=204)
def delete_shift(shift_id: int, _: object = Depends(require_admin_or_supervisor), db: Session = Depends(get_db)):
    s = db.query(Shift).filter(Shift.shift_id == shift_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Shift not found")

    invoice_link = db.query(InvoiceItem.item_id).filter(InvoiceItem.shift_id == shift_id).first()
    if invoice_link:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete shift already used in invoice items",
        )

    db.query(ShiftCalc).filter(ShiftCalc.shift_id == shift_id).delete()
    db.delete(s)
    db.commit()
    return

@router.post("/admin/shifts/create-closed")
def admin_create_closed_shift(payload: AdminCreateClosedShift,
                              db: Session = Depends(get_db),
                              _: object = Depends(require_admin_or_supervisor)):
    client = db.query(Client).filter(Client.client_id == payload.client_id).first()
    if not client:
        raise HTTPException(404, "Client not found")
    cg = db.query(Caregiver).filter(Caregiver.caregiver_id == payload.caregiver_id).first()
    if not cg:
        raise HTTPException(404, "Caregiver not found")

    tzname = client.timezone or settings.TIMEZONE
    start_utc = local_date_time_to_utc_iso(payload.start_date, payload.start_time, tzname)
    end_utc   = local_date_time_to_utc_iso(payload.end_date, payload.end_time, tzname)
    if end_utc <= start_utc:
        raise HTTPException(400, "End must be after start")

    # create shift
    s = Shift(
        client_id=payload.client_id,
        caregiver_id=payload.caregiver_id,
        start_date=payload.start_date, start_time=payload.start_time,
        end_date=payload.end_date,     end_time=payload.end_time,
        check_in_ts=start_utc, check_out_ts=end_utc,
        status="CLOSED",
        notes=payload.notes or "",
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    try:
        db.add(s)
        db.flush()
    except IntegrityError as e:
        db.rollback()
        if "overlap" in str(e.orig).lower():
            raise HTTPException(status_code=409, detail="Caregiver already has a shift during this time")
        raise HTTPException(status_code=400, detail=str(e.orig))

    # compute and store calc
    sc = compute_shift_calc(db, s.shift_id)  # should fill ShiftCalc with hours_day/night/total + pay fields
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        if "overlap" in str(e.orig).lower():
            raise HTTPException(status_code=409, detail="Caregiver already has a shift during this time")
        raise HTTPException(status_code=400, detail=str(e.orig))
    db.refresh(s)
    return {
        "shift_id": s.shift_id,
        "caregiver_id": s.caregiver_id,
        "client_id": s.client_id,
        "start": s.start_date + " " + s.start_time,
        "end":   s.end_date   + " " + s.end_time,
        "status": s.status
    }


@router.post("/admin/shifts/{shift_id}/recalculate", response_model=dict)
def recalculate_shift(
    shift_id: int,
    _: object = Depends(require_admin_or_supervisor),
    db: Session = Depends(get_db),
):
    s = db.query(Shift).filter(Shift.shift_id == shift_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Shift not found")
    if s.status != "CLOSED" or not s.check_in_ts or not s.check_out_ts:
        raise HTTPException(status_code=400, detail="Only closed shifts can be recalculated")

    client = db.query(Client).filter(Client.client_id == s.client_id).first()
    if not client:
        raise HTTPException(status_code=400, detail="Client not found")

    compute_shift_calc(db, s.shift_id)

    db.commit()
    db.refresh(s)
    return _shift_row_to_dict(s)