from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List, Dict

from app.db.session import get_db
from app.api.dependencies import require_caregiver
from app.models.tables import Shift, ShiftCalc
from app.services.time_utils import local_range_to_utc_bounds
from app.core.config import settings

router = APIRouter()

def _must(s: Optional[str], name: str) -> str:
    if not s or not s.strip():
        raise HTTPException(status_code=400, detail=f"{name} is required")
    return s.strip()

@router.get("/pay/summary")
def pay_summary(
        from_date: Optional[str] = Query(None, description="YYYY-MM-DD (local)"),
        from_time: Optional[str] = Query(None, description="HH:MM (24h, local)"),
        to_date:   Optional[str] = Query(None, description="YYYY-MM-DD (local)"),
        to_time:   Optional[str] = Query(None, description="HH:MM (24h, local)"),
        deps=Depends(require_caregiver),
        db: Session = Depends(get_db),
) -> Dict:
    """
    Summarize CLOSED shifts for the logged-in caregiver between a local date+time range.
    Range applies to Shift.check_in_ts (converted to UTC).
    """
    _, caregiver = deps
    try:
        start_utc, end_utc = local_range_to_utc_bounds(
            _must(from_date, "from_date"),
            _must(from_time, "from_time"),
            _must(to_date,   "to_date"),
            _must(to_time,   "to_time"),
            settings.TIMEZONE,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    q = (
        db.query(
            func.coalesce(func.sum(ShiftCalc.hours_total), 0.0).label("hours_total"),
            func.coalesce(func.sum(ShiftCalc.hours_day),   0.0).label("hours_day"),
            func.coalesce(func.sum(ShiftCalc.hours_night), 0.0).label("hours_night"),
            func.coalesce(func.sum(ShiftCalc.pay_day),     0.0).label("pay_day"),
            func.coalesce(func.sum(ShiftCalc.pay_night),   0.0).label("pay_night"),
            func.coalesce(func.sum(ShiftCalc.pay_total),   0.0).label("pay_total"),
        )
        .select_from(ShiftCalc)
        .join(Shift, Shift.shift_id == ShiftCalc.shift_id)
        .filter(Shift.caregiver_id == caregiver.caregiver_id)
        .filter(Shift.status == "CLOSED")
        .filter(Shift.check_in_ts >= start_utc)
        .filter(Shift.check_in_ts <  end_utc)
    )
    res = q.one()
    return {
        "from_date": from_date, "from_time": from_time,
        "to_date":   to_date,   "to_time":   to_time,
        "hours_total": round(res.hours_total or 0.0, 2),
        "hours_day":   round(res.hours_day   or 0.0, 2),
        "hours_night": round(res.hours_night or 0.0, 2),
        "pay_day":     round(res.pay_day     or 0.0, 2),
        "pay_night":   round(res.pay_night   or 0.0, 2),
        "pay_total":   round(res.pay_total   or 0.0, 2),
    }

@router.get("/pay/shifts")
def pay_shifts(
        from_date: Optional[str] = Query(None, description="YYYY-MM-DD (local)"),
        from_time: Optional[str] = Query(None, description="HH:MM (24h, local)"),
        to_date:   Optional[str] = Query(None, description="YYYY-MM-DD (local)"),
        to_time:   Optional[str] = Query(None, description="HH:MM (24h, local)"),
        deps=Depends(require_caregiver),
        db: Session = Depends(get_db),
) -> List[Dict]:
    """
    Detailed CLOSED shifts list in the given local date+time window (by check_in_ts).
    """
    _, caregiver = deps
    try:
        start_utc, end_utc = local_range_to_utc_bounds(
            _must(from_date, "from_date"),
            _must(from_time, "from_time"),
            _must(to_date,   "to_date"),
            _must(to_time,   "to_time"),
            settings.TIMEZONE,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    q = (
        db.query(Shift)
        .select_from(Shift)
        .join(ShiftCalc, ShiftCalc.shift_id == Shift.shift_id)
        .filter(Shift.caregiver_id == caregiver.caregiver_id)
        .filter(Shift.status == "CLOSED")
        .filter(Shift.check_in_ts >= start_utc)
        .filter(Shift.check_in_ts <  end_utc)
        .order_by(Shift.check_in_ts.asc())
    )

    rows = q.all()
    out: List[Dict] = []
    for s in rows:
        out.append({
            "shift_id": s.shift_id,
            "client_id": s.client_id,
            "caregiver_id": s.caregiver_id,
            "start_date": s.start_date, "start_time": s.start_time,
            "end_date": s.end_date,     "end_time": s.end_time,
            "status": s.status,
            "pay_total": round((s.calc.pay_total if s.calc and s.calc.pay_total is not None else 0.0), 2),
        })
    return out
