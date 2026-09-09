from __future__ import annotations
from datetime import date, datetime
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session

from app.models.tables import Shift, ShiftCalc, Client, PayRule, CaregiverClientRate
from app.core.config import settings
from app.services.calc_utils import split_day_night_local_tz
from app.services.holiday_utils import load_holiday_map, iter_local_date_slices, split_hours_day_night_local

# -------------------------------------------------------
# Helpers
# -------------------------------------------------------

def _localize(ts_iso: str, tzname: str) -> datetime:
    """Convert stored ISO UTC timestamp → timezone-aware local datetime."""
    dt = datetime.fromisoformat(ts_iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(ZoneInfo(tzname))


def _get_or_create_pay_rule_for_rate(
    db: Session,
    client_id: int,
    caregiver_id: int,
    rate_day: float,
    rate_night: float,
    day_window_start: str,
    day_window_end: str,
) -> PayRule:
    effective_start = str(date.today())
    rule_name = f"Caregiver {caregiver_id} Rate"

    latest: PayRule | None = (
        db.query(PayRule)
        .filter(PayRule.client_id == client_id, PayRule.rule_name == rule_name)
        .order_by(PayRule.effective_start.desc())
        .first()
    )

    if (
        latest
        and latest.effective_start == effective_start
        and float(latest.rate_day or 0.0) == float(rate_day)
        and float(latest.rate_night or 0.0) == float(rate_night)
        and latest.day_window_start == day_window_start
        and latest.day_window_end == day_window_end
    ):
        return latest

    pr = PayRule(
        client_id=client_id,
        rule_name=rule_name,
        rate_day=float(rate_day or 0.0),
        rate_night=float(rate_night or 0.0),
        day_window_start=day_window_start,
        day_window_end=day_window_end,
        overtime_after_hours=None,
        overtime_multiplier=None,
        effective_start=effective_start,
        effective_end=None,
    )
    db.add(pr)
    db.flush()
    return pr

# -------------------------------------------------------
# Main shift calculation service
# -------------------------------------------------------

def compute_shift_calc(db: Session, shift_id: int) -> ShiftCalc:
    """
    Recomputes ShiftCalc using:
      - Client time zone
            - Client-configured day/night window
            - Client-configured day/night rates
      - Split into day/night hours
        This enforces a single source of truth for all calculations.
    """
    shift: Shift | None = db.query(Shift).filter(Shift.shift_id == shift_id).first()
    if not shift:
        raise ValueError(f"No shift {shift_id} found")

    client: Client | None = db.query(Client).filter(Client.client_id == shift.client_id).first()
    if not client:
        raise ValueError(f"No client for shift {shift_id}")

        # Keep a pay-rule reference row for traceability, but calculations
        # must always use the current client-configured window and rates.
    day_window_start = client.day_window_start
    day_window_end = client.day_window_end
    if not day_window_start or not day_window_end:
        raise ValueError("Client day window parameters are required: day_window_start and day_window_end")

    rate_row: CaregiverClientRate | None = (
        db.query(CaregiverClientRate)
        .filter(
            CaregiverClientRate.caregiver_id == shift.caregiver_id,
            CaregiverClientRate.client_id == shift.client_id,
            CaregiverClientRate.is_custom == 1,
        )
        .first()
    )

    if not rate_row:
        raise ValueError(
            f"No pay rate configured for caregiver {shift.caregiver_id} and client {shift.client_id}. "
            "Set it in Caregivers -> Set Pay Rate by Caregiver + Client."
        )

    rate_day = float(rate_row.pay_day or 0.0)
    rate_night = float(rate_row.pay_night or 0.0)

    pay_rule = _get_or_create_pay_rule_for_rate(
        db=db,
        client_id=client.client_id,
        caregiver_id=shift.caregiver_id,
        rate_day=rate_day,
        rate_night=rate_night,
        day_window_start=day_window_start,
        day_window_end=day_window_end,
    )

    # Convert timestamps to local time
    tzname = client.timezone or settings.TIMEZONE
    local_in  = _localize(shift.check_in_ts, tzname)
    local_out = _localize(shift.check_out_ts, tzname)

    if local_out <= local_in:
        raise ValueError(f"Shift {shift_id} end <= start")

    # Load holiday pay multipliers for this client
    holiday_map = load_holiday_map(db, client.client_id)

    # Slice shift by local calendar day so each slice can carry its own holiday multiplier
    h_day = 0.0
    h_night = 0.0
    pay_day = 0.0
    pay_night = 0.0
    for slice_start, slice_end, date_str in iter_local_date_slices(local_in, local_out):
        sd, sn = split_hours_day_night_local(slice_start, slice_end, day_window_start, day_window_end)
        pay_mult = holiday_map.get(date_str, {}).get('pay', 1.0)
        h_day += sd
        h_night += sn
        pay_day += rate_day * sd * pay_mult
        pay_night += rate_night * sn * pay_mult

    pay_total = pay_day + pay_night

    # Upsert ShiftCalc row
    calc = db.query(ShiftCalc).filter(ShiftCalc.shift_id == shift_id).first()
    if calc is None:
        calc = ShiftCalc(
            shift_id=shift_id,
            hours_total=round(h_day + h_night, 4),
            hours_day=round(h_day, 4),
            hours_night=round(h_night, 4),
            hours_overtime=0.0,
            pay_day=round(pay_day, 2),
            pay_night=round(pay_night, 2),
            pay_overtime=0.0,
            pay_total=round(pay_total, 2),
            pay_rule_id=pay_rule.pay_rule_id,
            calc_version=1,
            calculated_at=datetime.utcnow().isoformat()
        )
        db.add(calc)
    else:
        calc.hours_total = round(h_day + h_night, 4)
        calc.hours_day = round(h_day, 4)
        calc.hours_night = round(h_night, 4)
        calc.hours_overtime = 0.0
        calc.pay_day = round(pay_day, 2)
        calc.pay_night = round(pay_night, 2)
        calc.pay_overtime = 0.0
        calc.pay_total = round(pay_total, 2)
        calc.pay_rule_id = pay_rule.pay_rule_id
        calc.calc_version = calc.calc_version + 1
        calc.calculated_at = datetime.utcnow().isoformat()

    return calc
