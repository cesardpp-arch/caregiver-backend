"""
Scheduler API: schedule assignment CRUD.
Endpoints:
  GET    /scheduler/assignments?client_id=&from_date=&to_date=
  POST   /scheduler/assignments
  DELETE /scheduler/assignments/{assignment_id}
  POST   /scheduler/assignments/copy-previous-month
"""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import get_current_user, get_db
from app.models.tables import ScheduleAssignment, User

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────────

class AssignmentCreate(BaseModel):
    client_id: int
    slot_id: int
    caregiver_id: int
    assign_date: str   # "YYYY-MM-DD"


class CopyPreviousMonthRequest(BaseModel):
    client_id: int
    target_month: str  # "YYYY-MM-DD" — any day in the target month (usually the 1st)


def _serialize(a: ScheduleAssignment) -> dict:
    return {
        "assignment_id": a.assignment_id,
        "client_id": a.client_id,
        "slot_id": a.slot_id,
        "caregiver_id": a.caregiver_id,
        "assign_date": a.assign_date,
        "caregiver_name": (a.caregiver.name if a.caregiver else None),
        "slot_name": (a.slot.slot_name if a.slot else None),
        "slot_start_time": (a.slot.start_time if a.slot else None),
        "slot_end_time": (a.slot.end_time if a.slot else None),
        "slot_rate_type": (a.slot.rate_type if a.slot else None),
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/scheduler/assignments")
def list_assignments(
    client_id: int = Query(...),
    from_date: str = Query(...),
    to_date: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(ScheduleAssignment)
        .filter(
            ScheduleAssignment.client_id == client_id,
            ScheduleAssignment.assign_date >= from_date,
            ScheduleAssignment.assign_date <= to_date,
        )
        .all()
    )
    return [_serialize(r) for r in rows]


@router.post("/scheduler/assignments", status_code=201)
def upsert_assignment(
    body: AssignmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Replace any existing assignment for this slot + date
    existing = (
        db.query(ScheduleAssignment)
        .filter(
            ScheduleAssignment.client_id == body.client_id,
            ScheduleAssignment.slot_id == body.slot_id,
            ScheduleAssignment.assign_date == body.assign_date,
        )
        .first()
    )
    if existing:
        existing.caregiver_id = body.caregiver_id
        db.commit()
        db.refresh(existing)
        return _serialize(existing)

    a = ScheduleAssignment(
        client_id=body.client_id,
        slot_id=body.slot_id,
        caregiver_id=body.caregiver_id,
        assign_date=body.assign_date,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return _serialize(a)


@router.post("/scheduler/assignments/copy-previous-month")
def copy_previous_month(
    body: CopyPreviousMonthRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete all assignments for the target month for this client, then
    copy assignments from the previous month mapping by day-of-week:
    the Nth occurrence of a weekday in the source month maps to the
    Nth occurrence of that same weekday in the target month.
    If the Nth occurrence doesn't exist (e.g. 5th Sunday), the last
    occurrence of that weekday in the target month is used instead.
    """
    import calendar as _cal

    try:
        anchor = date.fromisoformat(body.target_month)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid target_month format, expected YYYY-MM-DD")

    target_year, target_month_num = anchor.year, anchor.month
    target_last_day = _cal.monthrange(target_year, target_month_num)[1]
    target_start = date(target_year, target_month_num, 1)
    target_end = date(target_year, target_month_num, target_last_day)

    if target_month_num == 1:
        prev_year, prev_month_num = target_year - 1, 12
    else:
        prev_year, prev_month_num = target_year, target_month_num - 1
    prev_last_day = _cal.monthrange(prev_year, prev_month_num)[1]
    prev_start = date(prev_year, prev_month_num, 1)
    prev_end = date(prev_year, prev_month_num, prev_last_day)

    def map_by_weekday(src_date: date) -> date:
        """Return the date in target month with same weekday and nth occurrence."""
        src_weekday = src_date.weekday()          # 0=Mon … 6=Sun
        occurrence = (src_date.day - 1) // 7 + 1  # 1-based nth weekday in source month

        # First occurrence of src_weekday in target month
        first_day_weekday = date(target_year, target_month_num, 1).weekday()
        offset = (src_weekday - first_day_weekday) % 7
        first_occurrence_day = 1 + offset

        # Nth occurrence
        target_day = first_occurrence_day + (occurrence - 1) * 7

        # Clamp to last occurrence if Nth doesn't exist in target month
        if target_day > target_last_day:
            target_day -= 7

        return date(target_year, target_month_num, target_day)

    # Delete existing assignments in target month for this client
    db.query(ScheduleAssignment).filter(
        ScheduleAssignment.client_id == body.client_id,
        ScheduleAssignment.assign_date >= str(target_start),
        ScheduleAssignment.assign_date <= str(target_end),
    ).delete(synchronize_session=False)

    # Fetch previous month assignments
    prev_assignments = db.query(ScheduleAssignment).filter(
        ScheduleAssignment.client_id == body.client_id,
        ScheduleAssignment.assign_date >= str(prev_start),
        ScheduleAssignment.assign_date <= str(prev_end),
    ).all()

    created = 0
    skipped_duplicates = 0
    pending_keys: set[tuple[int, int, str]] = set()

    for a in prev_assignments:
        try:
            src_date = date.fromisoformat(a.assign_date)
        except ValueError:
            continue
        new_date = map_by_weekday(src_date)
        new_date_str = str(new_date)
        dedupe_key = (body.client_id, a.slot_id, new_date_str)

        # Important: SessionLocal has autoflush=False, so rows added in this loop
        # are not visible to the DB query below until commit/flush. Track keys in memory.
        if dedupe_key in pending_keys:
            skipped_duplicates += 1
            continue

        # Skip duplicates (same client+slot+date)
        exists = db.query(ScheduleAssignment).filter(
            ScheduleAssignment.client_id == body.client_id,
            ScheduleAssignment.slot_id == a.slot_id,
            ScheduleAssignment.assign_date == new_date_str,
        ).first()
        if not exists:
            db.add(ScheduleAssignment(
                client_id=body.client_id,
                slot_id=a.slot_id,
                caregiver_id=a.caregiver_id,
                assign_date=new_date_str,
            ))
            pending_keys.add(dedupe_key)
            created += 1
        else:
            skipped_duplicates += 1

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Copy conflict detected for one or more slot/date rows. Please retry.",
        )
    return {
        "copied": created,
        "skipped_duplicates": skipped_duplicates,
        "target_month": str(target_start),
    }


@router.delete("/scheduler/assignments/{assignment_id}", status_code=204)
def delete_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    a = db.query(ScheduleAssignment).filter(
        ScheduleAssignment.assignment_id == assignment_id
    ).first()
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    db.delete(a)
    db.commit()
