from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.dependencies import require_caregiver
from app.schemas.shift import CheckInRequest, CheckOutRequest, ShiftOut
from app.models.tables import Shift, Client, Caregiver, CaregiverClientRate
from app.services.time_utils import combine_local_to_utc_iso
from app.services.paycalc_service import compute_shift_calc
from app.core.config import settings

router = APIRouter()


def _raise_shift_guardrail_http_error(err: IntegrityError) -> None:
    msg = str(getattr(err, "orig", err))
    if "Caregiver overlap with another shift" in msg:
        raise HTTPException(
            status_code=409,
            detail="This shift overlaps another one for this caregiver. Adjust start/end time.",
        )
    if "Shift end must be after start" in msg:
        raise HTTPException(status_code=400, detail="Shift end must be after start")
    raise HTTPException(status_code=400, detail="Shift violates scheduling guardrails")


@router.post("/shifts/check-out/warnings", response_model=dict)
def check_out_warnings(payload: CheckOutRequest, deps=Depends(require_caregiver), db: Session = Depends(get_db)):
    user, caregiver = deps
    s = db.query(Shift).filter(Shift.caregiver_id == caregiver.caregiver_id, Shift.status == "OPEN").first()
    if not s:
        raise HTTPException(status_code=400, detail="No open shift to check out")

    client = db.query(Client).filter(Client.client_id == s.client_id).first()
    if not client:
        raise HTTPException(status_code=400, detail="Client not found")

    tzname = client.timezone or settings.TIMEZONE
    if bool(payload.start_date) != bool(payload.start_time):
        raise HTTPException(status_code=400, detail="Both start_date and start_time are required when updating check-in")

    effective_check_in_iso = s.check_in_ts
    if payload.start_date and payload.start_time:
        try:
            effective_check_in_iso = combine_local_to_utc_iso(payload.start_date, payload.start_time, tzname)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid start_date/start_time: {e}")

    try:
        check_out_iso = combine_local_to_utc_iso(payload.end_date, payload.end_time, tzname)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid end_date/end_time: {e}")

    overlap_rows = (
        db.query(Shift, Caregiver)
        .join(Caregiver, Caregiver.caregiver_id == Shift.caregiver_id)
        .filter(Shift.client_id == s.client_id)
        .filter(Shift.caregiver_id != caregiver.caregiver_id)
        .filter(Shift.status != "VOID")
        .filter(Shift.check_in_ts < check_out_iso)
        .filter((Shift.check_out_ts.is_(None)) | (Shift.check_out_ts > effective_check_in_iso))
        .order_by(Shift.check_in_ts.asc())
        .all()
    )

    overlaps = []
    for other_shift, other_cg in overlap_rows:
        overlaps.append({
            "shift_id": other_shift.shift_id,
            "caregiver_id": other_shift.caregiver_id,
            "caregiver_name": other_cg.name,
            "start_date": other_shift.start_date,
            "start_time": other_shift.start_time,
            "end_date": other_shift.end_date,
            "end_time": other_shift.end_time,
            "status": other_shift.status,
        })

    return {
        "has_overlap": len(overlaps) > 0,
        "overlap_count": len(overlaps),
        "overlaps": overlaps,
    }

@router.get("/shifts/clients", response_model=list[dict])
def list_active_clients(deps=Depends(require_caregiver), db: Session = Depends(get_db)):
    """Return active clients so caregivers can pick one on check-in."""
    rows = db.query(Client).filter(Client.active == 1).order_by(Client.name.asc()).all()
    return [{
        "client_id": c.client_id,
        "name": c.name,
        "bill_day": c.bill_day,
        "bill_night": c.bill_night,
        "day_window_start": c.day_window_start,
        "day_window_end": c.day_window_end,
        "timezone": c.timezone,        "invoice_anchor_dow": c.invoice_anchor_dow,
        "invoice_anchor_time": c.invoice_anchor_time,    } for c in rows]

@router.post("/shifts/check-in", response_model=ShiftOut)
def check_in(payload: CheckInRequest, deps=Depends(require_caregiver), db: Session = Depends(get_db)):
    user, caregiver = deps

    client = db.query(Client).filter(Client.client_id == payload.client_id, Client.active == 1).first()
    if not client:
        raise HTTPException(status_code=400, detail="Client not found or inactive")

    rate_row = (
        db.query(CaregiverClientRate)
        .filter(
            CaregiverClientRate.caregiver_id == caregiver.caregiver_id,
            CaregiverClientRate.client_id == payload.client_id,
            CaregiverClientRate.is_custom == 1,
        )
        .first()
    )
    if not rate_row:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No pay rate configured for caregiver {caregiver.caregiver_id} and client {payload.client_id}. "
                "Set it in Caregivers -> Set Pay Rate by Caregiver + Client."
            ),
        )

    existing = db.query(Shift).filter(Shift.caregiver_id == caregiver.caregiver_id, Shift.status == "OPEN").first()
    if existing:
        raise HTTPException(status_code=400, detail="You already have an open shift")

    tzname = client.timezone or settings.TIMEZONE
    try:
        check_in_iso = combine_local_to_utc_iso(payload.start_date, payload.start_time, tzname)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid start_date/start_time: {e}")

    s = Shift(
        client_id=client.client_id,
        caregiver_id=caregiver.caregiver_id,
        # store local fields too
        start_date=payload.start_date,
        start_time=payload.start_time,
        check_in_ts=check_in_iso,  # still store UTC
        check_out_ts=None,
        status="OPEN",
        notes=payload.notes or "",
        created_by=user.user_id,
        updated_by=user.user_id,
        created_at=check_in_iso,
        updated_at=check_in_iso,
    )
    db.add(s)
    try:
        db.commit()
    except IntegrityError as err:
        db.rollback()
        _raise_shift_guardrail_http_error(err)
    db.refresh(s)
    return ShiftOut(
        shift_id=s.shift_id,
        client_id=s.client_id,
        caregiver_id=s.caregiver_id,
        start_date=s.start_date,
        start_time=s.start_time,
        end_date=s.end_date,
        end_time=s.end_time,
        status=s.status,
        pay_total=None
    )

@router.post("/shifts/check-out", response_model=ShiftOut)
def check_out(payload: CheckOutRequest, deps=Depends(require_caregiver), db: Session = Depends(get_db)):
    user, caregiver = deps
    s = db.query(Shift).filter(Shift.caregiver_id == caregiver.caregiver_id, Shift.status == "OPEN").first()
    if not s:
        raise HTTPException(status_code=400, detail="No open shift to check out")

    client = db.query(Client).filter(Client.client_id == s.client_id).first()
    if not client:
        raise HTTPException(status_code=400, detail="Client not found")

    tzname = client.timezone or settings.TIMEZONE
    if bool(payload.start_date) != bool(payload.start_time):
        raise HTTPException(status_code=400, detail="Both start_date and start_time are required when updating check-in")

    effective_start_date = s.start_date
    effective_start_time = s.start_time
    effective_check_in_iso = s.check_in_ts
    if payload.start_date and payload.start_time:
        effective_start_date = payload.start_date
        effective_start_time = payload.start_time
        try:
            effective_check_in_iso = combine_local_to_utc_iso(payload.start_date, payload.start_time, tzname)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid start_date/start_time: {e}")

    try:
        check_out_iso = combine_local_to_utc_iso(payload.end_date, payload.end_time, tzname)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid end_date/end_time: {e}")

    if check_out_iso <= effective_check_in_iso:
        raise HTTPException(
            status_code=400,
            detail=(
                "Checkout must be after check-in. "
                f"Check-in: {effective_start_date} {effective_start_time}. "
                f"Requested checkout: {payload.end_date} {payload.end_time}."
            ),
        )

    s.start_date = effective_start_date
    s.start_time = effective_start_time
    s.check_in_ts = effective_check_in_iso
    s.check_out_ts = check_out_iso
    s.end_date = payload.end_date
    s.end_time = payload.end_time
    if payload.notes:
        s.notes = payload.notes
    s.status = "CLOSED"
    s.updated_by = user.user_id
    s.updated_at = check_out_iso
    db.add(s)
    db.flush()

    try:
        calc = compute_shift_calc(db, s.shift_id)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    try:
        db.commit()
    except IntegrityError as err:
        db.rollback()
        _raise_shift_guardrail_http_error(err)
    db.refresh(s)

    return ShiftOut(
        shift_id=s.shift_id,
        client_id=s.client_id,
        caregiver_id=s.caregiver_id,
        start_date=s.start_date,
        start_time=s.start_time,
        end_date=s.end_date,
        end_time=s.end_time,
        status=s.status,
        notes=s.notes,
        pay_total=calc.pay_total
    )

@router.get("/shifts/mine", response_model=list[ShiftOut])
def my_shifts(from_dt: str | None = Query(None), to_dt: str | None = Query(None), deps=Depends(require_caregiver), db: Session = Depends(get_db)):
    _, caregiver = deps
    q = db.query(Shift).filter(Shift.caregiver_id == caregiver.caregiver_id)
    if from_dt:
        q = q.filter(Shift.check_in_ts >= from_dt)
    if to_dt:
        q = q.filter(Shift.check_in_ts < to_dt)
    q = q.order_by(Shift.check_in_ts.desc())
    rows = q.all()

    out = []
    for s in rows:
        total = s.calc.pay_total if s.calc else None
        out.append(ShiftOut(
            shift_id=s.shift_id,
            client_id=s.client_id,
            caregiver_id=s.caregiver_id,
            start_date=s.start_date,
            start_time=s.start_time,
            end_date=s.end_date,
            end_time=s.end_time,
            status=s.status,
            pay_total=(s.calc.pay_total if s.calc else None),
        ))
    return out
@router.get("/shifts/open", response_model=ShiftOut)
def my_open_shift(deps=Depends(require_caregiver), db: Session = Depends(get_db)):
    _, caregiver = deps
    s = db.query(Shift).filter(Shift.caregiver_id == caregiver.caregiver_id, Shift.status == "OPEN").first()
    if not s:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No open shift")
    return ShiftOut(
        shift_id=s.shift_id,
        client_id=s.client_id,
        caregiver_id=s.caregiver_id,
        start_date=s.start_date,
        start_time=s.start_time,
        end_date=s.end_date,
        end_time=s.end_time,
        status=s.status,
        pay_total=(s.calc.pay_total if s.calc else None),
    )
