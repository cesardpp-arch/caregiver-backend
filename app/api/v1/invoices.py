from fastapi import APIRouter, Depends, HTTPException, Query, Path
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import exists
from typing import Optional, List, Dict
from datetime import datetime, timedelta, timezone

from app.api.dependencies import require_admin_or_supervisor
from app.db.session import get_db
from app.models.tables import Shift, ShiftCalc, Client, Invoice, InvoiceItem, Caregiver
from app.services.time_utils import local_range_to_utc_bounds
from app.core.config import settings


from zoneinfo import ZoneInfo
from app.services.holiday_utils import (
    load_holiday_map,
    iter_local_date_slices,
    split_hours_day_night_local,
)




router = APIRouter()

def calculate_invoice_number(from_date: str) -> int:
    try:
        dt = datetime.fromisoformat(from_date)
    except ValueError:
        try:
            dt = datetime.strptime(from_date, "%Y-%m-%d")
        except ValueError:
            raise ValueError("from_date must be YYYY-MM-DD")

    week_start = datetime(2026, 1, 4)
    week_number = 1
    while dt >= week_start + timedelta(days=7):
        week_start += timedelta(days=7)
        week_number += 1
    return week_number


def _req(x: Optional[str], name: str) -> str:
    if not x or not x.strip():
        raise HTTPException(status_code=400, detail=f"{name} is required")
    return x.strip()

def _get_invoice_or_404(db: Session, invoice_id: int) -> Invoice:
    inv = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return inv


def create_invoice_from_report(
    client_id: int,
    from_date: str,
    from_time: str,
    to_date: str,
    to_time: str,
    notes: Optional[str] = None,
    _=None,
    db: Optional[Session] = None,
):
    if db is None:
        raise ValueError("db session is required")

    client: Client | None = db.query(Client).filter(Client.client_id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    try:
        start_utc_str, end_utc_str = local_range_to_utc_bounds(
            from_date,
            from_time,
            to_date,
            to_time,
            client.timezone or settings.TIMEZONE,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    start_utc = datetime.fromisoformat(start_utc_str)
    end_utc = datetime.fromisoformat(end_utc_str)

    if end_utc <= start_utc:
        raise HTTPException(status_code=400, detail="to_datetime must be after from_datetime")

    bill_day = float(client.bill_day or 0.0)
    bill_night = float(client.bill_night or 0.0)
    tz = ZoneInfo(client.timezone or settings.TIMEZONE)
    holiday_map = load_holiday_map(db, client.client_id)
    day_window_start = client.day_window_start or "07:00"
    day_window_end = client.day_window_end or "23:00"

    shifts = (
        db.query(Shift, ShiftCalc)
        .join(ShiftCalc, ShiftCalc.shift_id == Shift.shift_id)
        .filter(Shift.client_id == client.client_id)
        .filter(Shift.status == "CLOSED")
        .filter(Shift.check_in_ts < end_utc_str)
        .filter(Shift.check_out_ts > start_utc_str)
        .order_by(Shift.check_in_ts.asc())
        .all()
    )
    if not shifts:
        raise HTTPException(status_code=400, detail="No closed shifts found overlapping this window")

    inv = Invoice(
        client_id=client_id,
        from_utc=start_utc_str,
        to_utc=end_utc_str,
        created_at=datetime.now(timezone.utc).isoformat(),
        total_amount=0.0,
        notes=notes or "",
        status="FINALIZED",
    )
    db.add(inv)
    db.flush()

    total_amount = 0.0
    items_added = 0
    shifts_skipped: list[int] = []

    for s, sc in shifts:
        if db.query(exists().where(InvoiceItem.shift_id == s.shift_id)).scalar():
            shifts_skipped.append(s.shift_id)
            continue

        try:
            in_utc = datetime.fromisoformat(s.check_in_ts)
            out_utc = datetime.fromisoformat(s.check_out_ts) if s.check_out_ts else None
        except Exception:
            shifts_skipped.append(s.shift_id)
            continue

        if out_utc is None or out_utc <= in_utc:
            shifts_skipped.append(s.shift_id)
            continue

        seg_start_utc = max(in_utc, start_utc)
        seg_end_utc = min(out_utc, end_utc)
        if seg_end_utc <= seg_start_utc:
            shifts_skipped.append(s.shift_id)
            continue

        seg_start_local = seg_start_utc.astimezone(tz)
        seg_end_local = seg_end_utc.astimezone(tz)

        amount = 0.0
        hours_day_total = 0.0
        hours_night_total = 0.0

        for slice_start, slice_end, ymd in iter_local_date_slices(seg_start_local, seg_end_local):
            h_day, h_night = split_hours_day_night_local(slice_start, slice_end, day_window_start, day_window_end)
            bill_mult = holiday_map.get(ymd, {}).get("bill", 1.0)
            amount += (h_day * bill_day + h_night * bill_night) * bill_mult
            hours_day_total += h_day
            hours_night_total += h_night

        item = InvoiceItem(
            invoice_id=inv.invoice_id,
            shift_id=s.shift_id,
            desc=f"{seg_start_local.strftime('%Y-%m-%d %H:%M')} – {seg_end_local.strftime('%Y-%m-%d %H:%M')}",
            hours_day=round(hours_day_total, 4),
            hours_night=round(hours_night_total, 4),
            rate_day=bill_day,
            rate_night=bill_night,
            amount=round(amount, 2),
        )
        db.add(item)
        total_amount += item.amount
        items_added += 1

    if items_added == 0:
        db.rollback()
        raise HTTPException(status_code=400, detail="All overlapping shifts are already billed or invalid")

    inv.total_amount = round(total_amount, 2)
    db.add(inv)
    db.commit()
    db.refresh(inv)

    return {
        "invoice_id": inv.invoice_id,
        "client_id": inv.client_id,
        "from_utc": inv.from_utc,
        "to_utc": inv.to_utc,
        "created_at": inv.created_at,
        "total_amount": inv.total_amount,
        "status": inv.status,
        "items_added": items_added,
        "shifts_skipped": shifts_skipped,
    }


# -------------------------------------------------------------------
# Create invoice for a client using local date+time window
# - includes CLOSED shifts for that client whose check_in_ts is in window
# - skips shifts already billed (unique index prevents duplicates)
# - uses client.bill_day / bill_night for amounts
# -------------------------------------------------------------------
@router.post("/invoices", response_model=dict)
def create_invoice(
    client_id: int = Query(...),
    from_date: str = Query(..., description="YYYY-MM-DD (local)"),
    from_time: str = Query(..., description="HH:MM 24h (local)"),
    to_date:   str = Query(..., description="YYYY-MM-DD (local)"),
    to_time:   str = Query(..., description="HH:MM 24h (local)"),
    notes: Optional[str] = None,
    _: object = Depends(require_admin_or_supervisor),
    db = Depends(get_db),
):
    return create_invoice_from_report(
        client_id=client_id,
        from_date=from_date,
        from_time=from_time,
        to_date=to_date,
        to_time=to_time,
        notes=notes,
        _=_,
        db=db,
    )

@router.get("/invoices", response_model=List[Dict])
def list_invoices(
        client_id: Optional[int] = Query(None),
        from_date: Optional[str] = Query(None),
        to_date: Optional[str] = Query(None),
        _: object = Depends(require_admin_or_supervisor),
        db: Session = Depends(get_db),
):
    q = db.query(Invoice).order_by(Invoice.invoice_id.desc())
    if client_id:
        q = q.filter(Invoice.client_id == client_id)
    if from_date:
        q = q.filter(Invoice.from_utc >= f"{from_date}T00:00:00")
    if to_date:
        q = q.filter(Invoice.to_utc <= f"{to_date}T23:59:59")
    out = []
    for inv in q.all():
        from_date = inv.from_utc[:10] if inv.from_utc else None
        to_date = inv.to_utc[:10] if inv.to_utc else None
        out.append({
            "invoice_id": inv.invoice_id,
            "client_id": inv.client_id,
            "from_utc": inv.from_utc,
            "to_utc": inv.to_utc,
            "from_date": from_date,
            "to_date": to_date,
            "created_at": inv.created_at,
            "total_amount": inv.total_amount,
            "invoice_number": calculate_invoice_number(from_date) if from_date else None,
            "status": inv.status,
            "notes": inv.notes,
        })
    return out

@router.get("/invoices/{invoice_id}", response_model=dict)
def invoice_detail(
        invoice_id: int,
        _: object = Depends(require_admin_or_supervisor),
        db: Session = Depends(get_db),
):
    inv = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    items = (
        db.query(InvoiceItem)
        .filter(InvoiceItem.invoice_id == inv.invoice_id)
        .order_by(InvoiceItem.item_id.asc())
        .all()
    )
    summary_rows = []
    detail_rows = []
    grouped = {}

    for it in items:
        shift = db.query(Shift).filter(Shift.shift_id == it.shift_id).first()
        caregiver = None
        if shift and shift.caregiver_id:
            caregiver = db.query(Caregiver).filter(Caregiver.caregiver_id == shift.caregiver_id).first()

        detail_rows.append({
            "item_id": it.item_id,
            "shift_id": it.shift_id,
            "desc": it.desc,
            "hours_day": it.hours_day,
            "hours_night": it.hours_night,
            "hours_total": round((it.hours_day or 0.0) + (it.hours_night or 0.0), 2),
            "rate_day": it.rate_day,
            "rate_night": it.rate_night,
            "amount": it.amount,
            "caregiver_id": shift.caregiver_id if shift else None,
            "caregiver_name": caregiver.name if caregiver else None,
            "notes": shift.notes if shift else None,
            "start_date": shift.start_date if shift else None,
            "start_time": shift.start_time if shift else None,
            "end_date": shift.end_date if shift else None,
            "end_time": shift.end_time if shift else None,
        })

        if shift and shift.caregiver_id:
            key = shift.caregiver_id
            grouped.setdefault(key, {
                "caregiver_id": shift.caregiver_id,
                "caregiver_name": caregiver.name if caregiver else None,
                "hours_day": 0.0,
                "hours_night": 0.0,
                "hours_total": 0.0,
                "bill_total": 0.0,
            })
            grouped[key]["hours_day"] += float(it.hours_day or 0.0)
            grouped[key]["hours_night"] += float(it.hours_night or 0.0)
            grouped[key]["hours_total"] += float(it.hours_day or 0.0) + float(it.hours_night or 0.0)
            grouped[key]["bill_total"] += float(it.amount or 0.0)

    summary_rows = [
        {
            "caregiver_id": row["caregiver_id"],
            "caregiver_name": row["caregiver_name"],
            "hours_day": round(row["hours_day"], 2),
            "hours_night": round(row["hours_night"], 2),
            "hours_total": round(row["hours_total"], 2),
            "bill_total": round(row["bill_total"], 2),
        }
        for row in sorted(grouped.values(), key=lambda entry: (entry.get("caregiver_name") or ""))
    ]

    from_date = inv.from_utc[:10] if inv.from_utc else None
    to_date = inv.to_utc[:10] if inv.to_utc else None

    return {
        "invoice_id": inv.invoice_id,
        "client_id": inv.client_id,
        "from_utc": inv.from_utc,
        "to_utc": inv.to_utc,
        "from_date": from_date,
        "to_date": to_date,
        "created_at": inv.created_at,
        "total_amount": inv.total_amount,
        "invoice_number": calculate_invoice_number(from_date) if from_date else None,
        "summary_rows": summary_rows,
        "detail_rows": detail_rows,
        "items": [
            {
                "item_id": it.item_id,
                "shift_id": it.shift_id,
                "desc": it.desc,
                "hours_day": it.hours_day,
                "hours_night": it.hours_night,
                "rate_day": it.rate_day,
                "rate_night": it.rate_night,
                "amount": it.amount,
            } for it in items
        ]
    }

@router.get("/invoices/{invoice_id}.csv", response_class=PlainTextResponse)
def invoice_csv(
        invoice_id: int,
        _: object = Depends(require_admin_or_supervisor),
        db: Session = Depends(get_db),
):
    inv = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    items = (
        db.query(InvoiceItem)
        .filter(InvoiceItem.invoice_id == inv.invoice_id)
        .order_by(InvoiceItem.item_id.asc())
        .all()
    )

    header = ["item_id","shift_id","desc","hours_day","hours_night","rate_day","rate_night","amount"]
    lines = [",".join(header)]
    for it in items:
        row = [
            str(it.item_id),
            str(it.shift_id),
            (it.desc or "").replace(",", " "),
            f"{it.hours_day:.2f}",
            f"{it.hours_night:.2f}",
            f"{it.rate_day:.2f}",
            f"{it.rate_night:.2f}",
            f"{it.amount:.2f}",
        ]
        lines.append(",".join(row))

    # Trailer line with totals
    total = sum(it.amount or 0.0 for it in items)
    lines.append(f",,,,,,TOTAL,{total:.2f}")
    return PlainTextResponse("\n".join(lines), media_type="text/csv; charset=utf-8")

@router.delete("/invoices/{invoice_id}", status_code=204)
def delete_invoice(
        invoice_id: int,
        _: object = Depends(require_admin_or_supervisor),
        db: Session = Depends(get_db),
):
    inv = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    db.delete(inv)
    db.commit()
    return

@router.put("/invoices/{invoice_id}/finalize")
def finalize_invoice(invoice_id: int = Path(...), db: Session = Depends(get_db), _: object = Depends(require_admin_or_supervisor)):
    inv = _get_invoice_or_404(db, invoice_id)
    if inv.status in ("PAID", "VOID"):
        raise HTTPException(status_code=400, detail=f"Cannot finalize invoice with status {inv.status}")
    inv.status = "FINALIZED"
    db.add(inv); db.commit(); db.refresh(inv)
    return {"invoice_id": inv.invoice_id, "status": inv.status}

@router.put("/invoices/{invoice_id}/pay")
def pay_invoice(invoice_id: int = Path(...), db: Session = Depends(get_db), _: object = Depends(require_admin_or_supervisor)):
    inv = _get_invoice_or_404(db, invoice_id)
    if inv.status != "FINALIZED":
        raise HTTPException(status_code=400, detail="Only FINALIZED invoices can be marked PAID")
    inv.status = "PAID"
    db.add(inv); db.commit(); db.refresh(inv)
    return {"invoice_id": inv.invoice_id, "status": inv.status}

@router.put("/invoices/{invoice_id}/void")
def void_invoice(invoice_id: int = Path(...), db: Session = Depends(get_db), _: object = Depends(require_admin_or_supervisor)):
    inv = _get_invoice_or_404(db, invoice_id)
    if inv.status == "PAID":
        raise HTTPException(status_code=400, detail="Cannot VOID a PAID invoice")
    inv.status = "VOID"
    db.add(inv); db.commit(); db.refresh(inv)
    return {"invoice_id": inv.invoice_id, "status": inv.status}

@router.get("/invoices/by-status")
def list_invoices_by_status(status: str, db: Session = Depends(get_db), _: object = Depends(require_admin_or_supervisor)):
    status = status.upper()
    if status not in ("DRAFT", "FINALIZED", "PAID", "VOID"):
        raise HTTPException(status_code=400, detail="status must be one of DRAFT, FINALIZED, PAID, VOID")
    rows = (db.query(Invoice)
              .filter(Invoice.status == status)
              .order_by(Invoice.invoice_id.desc())
              .all())
    return [
        {
            "invoice_id": r.invoice_id,
            "client_id": r.client_id,
            "from_utc": r.from_utc,
            "to_utc": r.to_utc,
            "total_amount": r.total_amount,
            "status": r.status,
        } for r in rows
    ]

@router.post("/invoices/{invoice_id}/rebuild")
def rebuild_invoice(invoice_id: int = Path(...),
                    db: Session = Depends(get_db),
                    _: object = Depends(require_admin_or_supervisor)):
    inv = _get_invoice_or_404(db, invoice_id)
    
    if inv.status != "DRAFT":
        raise HTTPException(
            status_code=400,
            detail=f"Invoice not editable in status {inv.status}"
        )
    
    if inv.status != "DRAFT":
        raise HTTPException(status_code=400, detail="Only DRAFT invoices can be rebuilt")

    # delete existing items
    db.query(InvoiceItem).filter(InvoiceItem.invoice_id == invoice_id).delete()
    db.commit()

    # (Re)run your existing logic that collects CLOSED shifts overlapping [from_utc,to_utc),
    # splits segments, computes day/night, and inserts items.
    # You likely already have this in create; refactor into a helper and call it here.
    # After insert, recompute total_amount.
    # Example: _populate_invoice_items(db, inv)

    # Recompute total
    total = sum(x[0] for x in db.query(InvoiceItem.amount).filter(InvoiceItem.invoice_id == invoice_id).all())
    inv.total_amount = float(total or 0.0)
    db.add(inv); db.commit(); db.refresh(inv)
    return {"invoice_id": inv.invoice_id, "status": inv.status, "total_amount": inv.total_amount}