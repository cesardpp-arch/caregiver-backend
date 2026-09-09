from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.api.dependencies import require_admin_or_supervisor
from app.db.session import get_db
from app.models.tables import Client
from app.services.invoice_cycle import suggest_week_window

router = APIRouter()

@router.get("/invoices/suggest-window")
def suggest_window(
    client_id: int = Query(...),
    reference_date: str = Query(..., description="YYYY-MM-DD (local)"),
    _: object = Depends(require_admin_or_supervisor),
    db: Session = Depends(get_db),
):
    c = db.query(Client).filter(Client.client_id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")

    if (c.invoice_cycle or "WEEKLY").upper() != "WEEKLY":
        raise HTTPException(status_code=400, detail="Only WEEKLY cycles supported in suggestion helper")

    tz = c.timezone or "America/New_York"
    anchor_dow = c.invoice_anchor_dow if c.invoice_anchor_dow is not None else 6
    anchor_time = c.invoice_anchor_time or "23:00"

    start, end = suggest_week_window(reference_date, anchor_dow, anchor_time, tz)
    # Format as strings for convenience
    return {
        "client_id": client_id,
        "cycle": "WEEKLY",
        "anchor_dow": anchor_dow,
        "anchor_time": anchor_time,
        "timezone": tz,
        "from_date": start.strftime("%Y-%m-%d"),
        "from_time": start.strftime("%H:%M"),
        "to_date": end.strftime("%Y-%m-%d"),
        "to_time": end.strftime("%H:%M"),
    }
