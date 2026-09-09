from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, Tuple

from app.core.config import settings

# -------------------------------------------------------------
# Convert local date+time to UTC ISO string (used in shifts)
# -------------------------------------------------------------
def combine_local_to_utc_iso(local_date: str, local_time: str, tz_name: str) -> str:
    """
    Convert local date+time (YYYY-MM-DD, HH:MM) to an ISO UTC timestamp string.
    """
    try:
        d = datetime.strptime(local_date, "%Y-%m-%d").date()
    except Exception:
        raise ValueError("Invalid date format, must be YYYY-MM-DD")

    try:
        t = datetime.strptime(local_time, "%H:%M").time()
    except Exception:
        raise ValueError("Invalid time format, must be HH:MM in 24h format")

    try:
        zone = ZoneInfo(tz_name)
    except Exception:
        raise ValueError(f"Invalid timezone: {tz_name}")

    local_dt = datetime.combine(d, t, tzinfo=zone)
    utc_dt = local_dt.astimezone(ZoneInfo("UTC"))
    return utc_dt.isoformat()

# -------------------------------------------------------------
# Helpers used in check-in/out validation
# -------------------------------------------------------------
def parse_local_date(val: Optional[str]) -> Optional[date]:
    if not val:
        return None
    try:
        return datetime.strptime(val, "%Y-%m-%d").date()
    except Exception:
        raise ValueError("Date must be YYYY-MM-DD")

def parse_local_time(val: Optional[str]) -> Optional[time]:
    if not val:
        return None
    try:
        return datetime.strptime(val, "%H:%M").time()
    except Exception:
        raise ValueError("Time must be HH:MM in 24h format")

# -------------------------------------------------------------
# REQUIRED by pay.py and admin_reports.py
# Validates that all 4 input fields exist and builds UTC range
# -------------------------------------------------------------
def local_range_to_utc_bounds(
        from_date: Optional[str],
        from_time: Optional[str],
        to_date:   Optional[str],
        to_time:   Optional[str],
        tz_name: str,
) -> Tuple[str, str]:
    """
    Require full date + time for start and end.
    Convert both to UTC ISO strings.
    """
    if not (from_date and from_time and to_date and to_time):
        raise ValueError("from_date, from_time, to_date, to_time are all required.")

    start_utc = combine_local_to_utc_iso(from_date, from_time, tz_name)
    end_utc   = combine_local_to_utc_iso(to_date,   to_time,   tz_name)

    if end_utc <= start_utc:
        raise ValueError("End must be after start.")

    return start_utc, end_utc


def local_date_time_to_utc_iso(date_str: str, time_str: str, tzname: str) -> str:
    """
    Converts local YYYY-MM-DD and HH:MM to a UTC ISO string.
    """
    try:
        tz = ZoneInfo(tzname)
        dt_local = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        dt_local = dt_local.replace(tzinfo=tz)
        dt_utc = dt_local.astimezone(ZoneInfo("UTC"))
        return dt_utc.isoformat()
    except Exception as e:
        raise ValueError(f"Invalid local date/time: {e}")
    

def split_by_day_window_local(start_local: datetime, end_local: datetime,
                              day_start_hhmm: str, day_end_hhmm: str):
    def parse(hhmm: str):
        hh, mm = hhmm.split(":")
        return int(hh), int(mm)

    dsh, dsm = parse(day_start_hhmm)
    deh, dem = parse(day_end_hhmm)

    total_minutes = int((end_local - start_local).total_seconds() // 60)

    # Build absolute day window for the slice day
    day_start = start_local.replace(hour=dsh, minute=dsm, second=0, microsecond=0)
    day_end   = start_local.replace(hour=deh, minute=dem, second=0, microsecond=0)

    def overlap(a1, a2, b1, b2):
        s = max(a1, b1)
        e = min(a2, b2)
        return max(0, int((e - s).total_seconds() // 60))

    # Case A: simple window (day_start < day_end)
    if day_start < day_end:
        day_minutes = overlap(start_local, end_local, day_start, day_end)
    else:
        # Case B: window crosses midnight
        day_minutes = overlap(start_local, end_local, day_start,
                              start_local.replace(hour=23, minute=59, second=59))
        day_minutes += overlap(start_local, end_local,
                               start_local.replace(hour=0, minute=0, second=0),
                               day_end)

    night_minutes = total_minutes - day_minutes

    return round(day_minutes / 60.0, 4), round(night_minutes / 60.0, 4)

def combine_local_to_utc_dt(local_date: str, local_time: str, tz_name: str) -> datetime:
    d = datetime.strptime(local_date, "%Y-%m-%d").date()
    t = datetime.strptime(local_time, "%H:%M").time()
    zone = ZoneInfo(tz_name)
    local_dt = datetime.combine(d, t, tzinfo=zone)
    return local_dt.astimezone(ZoneInfo("UTC"))

def local_range_to_utc_bounds_dt(
        from_date: str,
        from_time: str,
        to_date:   str,
        to_time:   str,
        tz_name: str,
) -> Tuple[datetime, datetime]:
    start_utc = combine_local_to_utc_dt(from_date, from_time, tz_name)
    end_utc   = combine_local_to_utc_dt(to_date,   to_time,   tz_name)
    if end_utc <= start_utc:
        raise ValueError("End must be after start.")
    return start_utc, end_utc