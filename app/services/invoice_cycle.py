from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

def _start_of_day(d: datetime) -> datetime:
    return d.replace(hour=0, minute=0, second=0, microsecond=0)

def suggest_week_window(
    reference_local_date: str,  # "YYYY-MM-DD"
    anchor_dow: int,            # 0=Mon ... 6=Sun
    anchor_time: str,           # "HH:MM"
    tz: str                     # e.g., "America/New_York"
):
    tzinfo = ZoneInfo(tz)
    y, m, d = map(int, reference_local_date.split("-"))
    ref = datetime(y, m, d, tzinfo=tzinfo)

    # Find the most recent anchor day at anchor_time strictly <= ref
    # If ref is exactly on anchor day at or after anchor_time, that counts as window start.
    anchor_hour, anchor_min = map(int, anchor_time.split(":"))
    # go back to the anchor weekday
    days_back = (ref.weekday() - anchor_dow) % 7
    anchor_date = _start_of_day(ref) - timedelta(days=days_back)
    window_start = anchor_date.replace(hour=anchor_hour, minute=anchor_min)
    if ref < window_start:
        # if our ref is earlier that same anchor day/time, go one week back
        window_start -= timedelta(days=7)
    window_end = window_start + timedelta(days=7)
    return window_start, window_end
