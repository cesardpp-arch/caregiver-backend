from __future__ import annotations
from datetime import datetime, timedelta
from typing import Dict, Iterator, Tuple
from sqlalchemy.orm import Session

from app.models.tables import Holiday, Client

# ---- Holidays map loader ----
def load_holiday_map(db: Session, client_id: int) -> Dict[str, Dict[str, float]]:
    """
    Returns dict keyed by 'YYYY-MM-DD' (local date) with keys 'bill' and/or 'pay'.
    Client-specific rows override globals for the same date.
    """
    m: Dict[str, Dict[str, float]] = {}

    # Apply globals first.
    global_rows = (
        db.query(Holiday)
          .filter(Holiday.client_id.is_(None))
          .all()
    )
    for r in global_rows:
        key = (r.date or "").strip()
        if not key:
            continue
        m.setdefault(key, {})
        if r.multiplier_bill is not None:
            m[key]['bill'] = float(r.multiplier_bill)
        if r.multiplier_pay is not None:
            m[key]['pay'] = float(r.multiplier_pay)

    # Then apply client-specific rows so they deterministically override globals.
    client_rows = (
        db.query(Holiday)
          .filter(Holiday.client_id == client_id)
          .all()
    )
    for r in client_rows:
        key = (r.date or "").strip()  # expected 'YYYY-MM-DD'
        if not key:
            continue
        m.setdefault(key, {})
        if r.multiplier_bill is not None:
            m[key]['bill'] = float(r.multiplier_bill)
        if r.multiplier_pay is not None:
            m[key]['pay'] = float(r.multiplier_pay)
    return m

# ---- Local date slicer ----
def iter_local_date_slices(start_local: datetime, end_local: datetime) -> Iterator[Tuple[datetime, datetime, str]]:
    """
    Yields (slice_start_local, slice_end_local, slice_date_str) where each slice stays within a single local calendar day.
    """
    cur = start_local
    while cur < end_local:
        next_midnight = (cur.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))
        stop = min(end_local, next_midnight)
        yield cur, stop, cur.strftime("%Y-%m-%d")
        cur = stop

# ---- Day/Night splitter (local) ----
def split_hours_day_night_local(start_local: datetime, end_local: datetime, day_start_hhmm: str, day_end_hhmm: str) -> Tuple[float, float]:
    """
    Split [start_local, end_local) into (hours_day, hours_night) using a local daily window [day_start, day_end).
    Example window: 07:00–23:00 means 'day' is [07:00, 23:00), everything else is 'night'.
    """
    assert start_local <= end_local
    # normalize window to today's times (we'll iterate by minutes)
    def parse_hhmm(s: str) -> Tuple[int, int]:
        hh, mm = s.split(":")
        return int(hh), int(mm)

    day_h, day_m = parse_hhmm(day_start_hhmm)
    end_h, end_m = parse_hhmm(day_end_hhmm)

    # We’ll walk minute by minute only for boundary alignment via blocks to stay accurate but efficient.
    # To keep it light, compute overlap with day-block and night-block analytically per-slice-day:
    total_minutes = int((end_local - start_local).total_seconds() // 60)

    # Build this slice day's absolute day-window
    day_start = start_local.replace(hour=day_h, minute=day_m, second=0, microsecond=0)
    day_end = start_local.replace(hour=end_h, minute=end_m, second=0, microsecond=0)

    # If window crosses midnight (rare for typical 07–23), handle by splitting into two segments
    def overlap_minutes(a1: datetime, a2: datetime, b1: datetime, b2: datetime) -> int:
        s = max(a1, b1)
        e = min(a2, b2)
        return max(0, int((e - s).total_seconds() // 60))

    if day_start <= day_end:
        day_minutes = overlap_minutes(start_local, end_local, day_start, day_end)
    else:
        # window wraps midnight: day is [day_start -> 24:00) U [00:00 -> day_end)
        day_minutes = overlap_minutes(start_local, end_local, day_start, start_local.replace(hour=23, minute=59, second=59, microsecond=999999))
        day_minutes += overlap_minutes(start_local, end_local, start_local.replace(hour=0, minute=0, second=0, microsecond=0), day_end)

    night_minutes = total_minutes - day_minutes
    return round(day_minutes / 60.0, 4), round(night_minutes / 60.0, 4)
