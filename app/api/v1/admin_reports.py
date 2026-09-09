from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List, Dict
from datetime import datetime
from zoneinfo import ZoneInfo

from app.api.dependencies import require_reports_viewer
from app.db.session import get_db
from app.models.tables import Shift, ShiftCalc, Caregiver, Client, User
from app.services.time_utils import local_range_to_utc_bounds
from app.core.config import settings
from app.services.holiday_utils import load_holiday_map, iter_local_date_slices, split_hours_day_night_local

router = APIRouter()

def _must(s: Optional[str], name: str) -> str:
    if not s or not s.strip():
        raise HTTPException(status_code=400, detail=f"{name} is required")
    return s.strip()

# --------------------------------------------------------------------
# SUMMARY by caregiver within local date+time window (check_in_ts based)
# --------------------------------------------------------------------
@router.get("/admin/reports/payroll", response_model=List[Dict])
def payroll_summary(
        from_date: Optional[str] = Query(None, description="YYYY-MM-DD (local)"),
        from_time: Optional[str] = Query(None, description="HH:MM (24h, local)"),
        to_date:   Optional[str] = Query(None, description="YYYY-MM-DD (local)"),
        to_time:   Optional[str] = Query(None, description="HH:MM (24h, local)"),
        caregiver_id: Optional[int] = Query(None),
        client_id: Optional[int] = Query(None),
        user: User = Depends(require_reports_viewer),
        db: Session = Depends(get_db),
) -> List[Dict]:
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
            Shift.shift_id,
            Shift.caregiver_id,
            Shift.client_id,
            Shift.check_in_ts,
            Shift.check_out_ts,
            Caregiver.name.label("caregiver_name"),
            ShiftCalc.hours_day,
            ShiftCalc.hours_night,
            ShiftCalc.hours_total,
            ShiftCalc.pay_day,
            ShiftCalc.pay_night,
            ShiftCalc.pay_total,
            Client.bill_day,
            Client.bill_night,
            Client.holiday_bill_multiplier,
            Client.day_window_start,
            Client.day_window_end,
            Client.timezone,
        )
        .select_from(Shift)
        .join(ShiftCalc, ShiftCalc.shift_id == Shift.shift_id)
        .join(Caregiver, Caregiver.caregiver_id == Shift.caregiver_id)
        .join(Client, Client.client_id == Shift.client_id)
        .filter(Shift.status == "CLOSED")
        .filter(Shift.check_in_ts >= start_utc)
        .filter(Shift.check_in_ts <  end_utc)
    )
    if user.role == "CUSTOMER":
        if not getattr(user, "client_id", None):
            raise HTTPException(status_code=403, detail="Customer profile is missing linked client")
        client_id = user.client_id

    if caregiver_id:
        q = q.filter(Shift.caregiver_id == caregiver_id)
    if client_id:
        q = q.filter(Shift.client_id == client_id)

    rows = q.order_by(Caregiver.name.asc(), Shift.check_in_ts.asc()).all()

    holiday_cache: Dict[int, Dict[str, Dict[str, float]]] = {}
    grouped: Dict[int, Dict] = {}

    for r in rows:
        cg_id = int(r.caregiver_id)
        if cg_id not in grouped:
            grouped[cg_id] = {
                "caregiver_id": cg_id,
                "caregiver_name": r.caregiver_name,
                "hours_day": 0.0,
                "hours_night": 0.0,
                "hours_total": 0.0,
                "bill_day": 0.0,
                "bill_night": 0.0,
                "bill_total": 0.0,
                "pay_day": 0.0,
                "pay_night": 0.0,
                "pay_total": 0.0,
            }

        g = grouped[cg_id]
        g["hours_day"] += float(r.hours_day or 0.0)
        g["hours_night"] += float(r.hours_night or 0.0)
        g["hours_total"] += float(r.hours_total or 0.0)
        g["pay_day"] += float(r.pay_day or 0.0)
        g["pay_night"] += float(r.pay_night or 0.0)
        g["pay_total"] += float(r.pay_total or 0.0)

        client_id = int(r.client_id)
        if client_id not in holiday_cache:
            holiday_cache[client_id] = load_holiday_map(db, client_id)

        try:
            if not r.check_in_ts or not r.check_out_ts:
                continue
            tz_name = r.timezone or settings.TIMEZONE
            tz = ZoneInfo(tz_name)
            local_in = datetime.fromisoformat(r.check_in_ts).astimezone(tz)
            local_out = datetime.fromisoformat(r.check_out_ts).astimezone(tz)
            if local_out <= local_in:
                continue
        except Exception:
            continue

        day_window_start = r.day_window_start or "07:00"
        day_window_end = r.day_window_end or "23:00"
        bill_day_rate = float(r.bill_day or 0.0)
        bill_night_rate = float(r.bill_night or 0.0)
        holiday_map = holiday_cache[client_id]

        for slice_start, slice_end, ymd in iter_local_date_slices(local_in, local_out):
            h_day, h_night = split_hours_day_night_local(
                slice_start,
                slice_end,
                day_window_start,
                day_window_end,
            )
            bill_mult = holiday_map.get(ymd, {}).get("bill", 1.0)
            g["bill_day"] += h_day * bill_day_rate * bill_mult
            g["bill_night"] += h_night * bill_night_rate * bill_mult

    out: List[Dict] = []
    for row in sorted(grouped.values(), key=lambda x: (x.get("caregiver_name") or "").lower()):
        item = {
            "caregiver_id": row["caregiver_id"],
            "caregiver_name": row["caregiver_name"],
            "hours_day": round(row["hours_day"], 2),
            "hours_night": round(row["hours_night"], 2),
            "hours_total": round(row["hours_total"], 2),
            "bill_day": round(row["bill_day"], 2),
            "bill_night": round(row["bill_night"], 2),
            "bill_total": round(row["bill_day"] + row["bill_night"], 2),
        }
        if user.role != "CUSTOMER":
            item.update({
                "pay_day": round(row["pay_day"], 2),
                "pay_night": round(row["pay_night"], 2),
                "pay_total": round(row["pay_total"], 2),
            })
        out.append(item)

    return out

# --------------------------------------------------------------------
# DETAIL (per shift) within local date+time window (check_in_ts based)
# --------------------------------------------------------------------
@router.get("/admin/reports/payroll/detail", response_model=List[Dict])
def payroll_detail(
        from_date: Optional[str] = Query(None, description="YYYY-MM-DD (local)"),
        from_time: Optional[str] = Query(None, description="HH:MM (24h, local)"),
        to_date:   Optional[str] = Query(None, description="YYYY-MM-DD (local)"),
        to_time:   Optional[str] = Query(None, description="HH:MM (24h, local)"),
        caregiver_id: Optional[int] = Query(None),
        client_id: Optional[int] = Query(None),
        user: User = Depends(require_reports_viewer),
        db: Session = Depends(get_db),
) -> List[Dict]:
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
            Shift.shift_id,
            Shift.start_date, Shift.start_time,
            Shift.end_date,   Shift.end_time,
            Shift.client_id,  Shift.caregiver_id,
            Shift.notes,
            Caregiver.name.label("caregiver_name"),
            Client.name.label("client_name"),
            ShiftCalc.hours_day, ShiftCalc.hours_night, ShiftCalc.hours_total,
            ShiftCalc.pay_day, ShiftCalc.pay_night, ShiftCalc.pay_total,
        )
        .select_from(Shift)
        .join(ShiftCalc, ShiftCalc.shift_id == Shift.shift_id)
        .join(Caregiver, Caregiver.caregiver_id == Shift.caregiver_id)
        .join(Client, Client.client_id == Shift.client_id)
        .filter(Shift.status == "CLOSED")
        .filter(Shift.check_in_ts >= start_utc)
        .filter(Shift.check_in_ts <  end_utc)
        .order_by(Shift.check_in_ts.asc())
    )
    if user.role == "CUSTOMER":
        if not getattr(user, "client_id", None):
            raise HTTPException(status_code=403, detail="Customer profile is missing linked client")
        client_id = user.client_id

    if caregiver_id:
        q = q.filter(Shift.caregiver_id == caregiver_id)
    if client_id:
        q = q.filter(Shift.client_id == client_id)

    out: List[Dict] = []
    for r in q.all():
        row = {
            "shift_id": r.shift_id,
            "start_date": r.start_date, "start_time": r.start_time,
            "end_date":   r.end_date,   "end_time":   r.end_time,
            "client_id": r.client_id, "client_name": r.client_name,
            "caregiver_id": r.caregiver_id, "caregiver_name": r.caregiver_name,
            "notes": r.notes or '',
            "hours_day": round(r.hours_day or 0.0, 2),
            "hours_night": round(r.hours_night or 0.0, 2),
            "hours_total": round(r.hours_total or 0.0, 2),
        }
        if user.role != "CUSTOMER":
            row.update({
                "pay_day": round(r.pay_day or 0.0, 2),
                "pay_night": round(r.pay_night or 0.0, 2),
                "pay_total": round(r.pay_total or 0.0, 2),
            })
        out.append(row)
    return out

# --------------------------------------------------------------------
# CSV (same filters) within local date+time window
# --------------------------------------------------------------------
@router.get("/admin/reports/payroll/detail.csv", response_class=PlainTextResponse)
def payroll_detail_csv(
        from_date: Optional[str] = Query(None),
        from_time: Optional[str] = Query(None),
        to_date:   Optional[str] = Query(None),
        to_time:   Optional[str] = Query(None),
        caregiver_id: Optional[int] = Query(None),
        client_id: Optional[int] = Query(None),
        user: User = Depends(require_reports_viewer),
        db: Session = Depends(get_db),
) -> PlainTextResponse:
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
            Shift.shift_id,
            Shift.start_date, Shift.start_time,
            Shift.end_date,   Shift.end_time,
            Client.name.label("client_name"),
            Caregiver.name.label("caregiver_name"),
            ShiftCalc.hours_total, ShiftCalc.hours_day, ShiftCalc.hours_night,
            ShiftCalc.pay_total, ShiftCalc.pay_day, ShiftCalc.pay_night,
        )
        .select_from(Shift)
        .join(ShiftCalc, ShiftCalc.shift_id == Shift.shift_id)
        .join(Caregiver, Caregiver.caregiver_id == Shift.caregiver_id)
        .join(Client, Client.client_id == Shift.client_id)
        .filter(Shift.status == "CLOSED")
        .filter(Shift.check_in_ts >= start_utc)
        .filter(Shift.check_in_ts <  end_utc)
        .order_by(Shift.check_in_ts.asc())
    )
    if user.role == "CUSTOMER":
        if not getattr(user, "client_id", None):
            raise HTTPException(status_code=403, detail="Customer profile is missing linked client")
        client_id = user.client_id

    # optional extra filters
    if caregiver_id:
        q = q.filter(Shift.caregiver_id == caregiver_id)
    if client_id:
        q = q.filter(Shift.client_id == client_id)

    if user.role == "CUSTOMER":
        header = [
            "shift_id","start_date","start_time","end_date","end_time",
            "client_name","caregiver_name",
            "hours_total","hours_day","hours_night"
        ]
    else:
        header = [
            "shift_id","start_date","start_time","end_date","end_time",
            "client_name","caregiver_name",
            "hours_total","hours_day","hours_night",
            "pay_total","pay_day","pay_night"
        ]
    lines = [",".join(header)]
    for r in q.all():
        row = [
            str(r.shift_id or ""),
            r.start_date or "", r.start_time or "",
            r.end_date or "",   r.end_time or "",
            (r.client_name or "").replace(",", " "),
            (r.caregiver_name or "").replace(",", " "),
            f"{(r.hours_total or 0.0):.2f}",
            f"{(r.hours_day   or 0.0):.2f}",
            f"{(r.hours_night or 0.0):.2f}",
        ]
        if user.role != "CUSTOMER":
            row.extend([
                f"{(r.pay_total   or 0.0):.2f}",
                f"{(r.pay_day     or 0.0):.2f}",
                f"{(r.pay_night   or 0.0):.2f}",
            ])
        lines.append(",".join(row))
    return PlainTextResponse(content="\n".join(lines), media_type="text/csv; charset=utf-8")
