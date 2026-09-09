from datetime import datetime, time, timedelta, timezone
from dateutil import parser as dtparser
from zoneinfo import ZoneInfo
from app.services.holiday_utils import iter_local_date_slices, split_hours_day_night_local

def _parse_hhmm(s: str) -> time:
    hh, mm = s.split(":")
    return time(int(hh), int(mm))

def _hours(td: timedelta) -> float:
    return round(td.total_seconds() / 3600.0, 4)

def split_day_night(start_iso: str, end_iso: str, day_start: str, day_end: str):
    """Returns hours_day, hours_night."""
    start = dtparser.isoparse(start_iso)
    end = dtparser.isoparse(end_iso)
    if end <= start:
        return 0.0, 0.0

    day_s = _parse_hhmm(day_start)
    day_e = _parse_hhmm(day_end)

    cur = start
    hours_day = 0.0
    hours_night = 0.0

    while cur < end:
        # boundary: next minute
        nxt = min(
            datetime.combine(cur.date(), day_e, tzinfo=cur.tzinfo) if cur.time() < day_e else
            datetime.combine(cur.date() + timedelta(days=1), day_e, tzinfo=cur.tzinfo),
            end
        )

        # is cur within day window?
        day_window_start = datetime.combine(cur.date(), day_s, tzinfo=cur.tzinfo)
        day_window_end = datetime.combine(cur.date(), day_e, tzinfo=cur.tzinfo)
        in_day = day_window_start <= cur < day_window_end

        delta = min(nxt, end) - cur
        if in_day:
            hours_day += _hours(delta)
        else:
            hours_night += _hours(delta)

        # move to next split point
        # jump to either end of current window or next minute to avoid infinite loop
        cur = min(nxt, end)

    return round(hours_day, 2), round(hours_night, 2)

def compute_pay(hours_day: float, hours_night: float, rate_day: float, rate_night: float) -> tuple[float, float, float]:
    pay_day = round(hours_day * float(rate_day), 2)
    pay_night = round(hours_night * float(rate_night), 2)
    total = round(pay_day + pay_night, 2)
    return pay_day, pay_night, total


def split_day_night_local_tz(
    start_iso: str,
    end_iso: str,
    day_start: str,
    day_end: str,
    tzname: str,
) -> tuple[float, float]:
    """Split UTC ISO timestamps into day/night hours using client-local timezone windows."""
    start_utc = dtparser.isoparse(start_iso)
    end_utc = dtparser.isoparse(end_iso)
    if end_utc <= start_utc:
        return 0.0, 0.0

    tz = ZoneInfo(tzname)
    start_local = start_utc.astimezone(tz)
    end_local = end_utc.astimezone(tz)

    total_day = 0.0
    total_night = 0.0
    for slice_start, slice_end, _ in iter_local_date_slices(start_local, end_local):
        h_day, h_night = split_hours_day_night_local(slice_start, slice_end, day_start, day_end)
        total_day += h_day
        total_night += h_night

    return round(total_day, 2), round(total_night, 2)
