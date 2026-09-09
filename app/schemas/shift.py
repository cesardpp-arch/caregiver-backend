from pydantic import BaseModel, Field
from typing import Optional

class CheckInRequest(BaseModel):
    client_id: int = Field(..., description="Client the shift is for")
    start_date: str = Field(..., description="YYYY-MM-DD (local org time)")
    start_time: str = Field(..., description="HH:MM (24h, local org time)")
    notes: Optional[str] = None

class CheckOutRequest(BaseModel):
    start_date: Optional[str] = Field(None, description="Optional updated check-in date YYYY-MM-DD (local org time)")
    start_time: Optional[str] = Field(None, description="Optional updated check-in time HH:MM (24h, local org time)")
    end_date: str = Field(..., description="YYYY-MM-DD (local org time)")
    end_time: str = Field(..., description="HH:MM (24h, local org time)")
    notes: Optional[str] = Field(None, description="Optional shift notes (unusual situations, etc)")

class ShiftOut(BaseModel):
    shift_id: int
    client_id: int
    caregiver_id: int
    # local-friendly fields you want to see
    start_date: str | None = None
    start_time: str | None = None
    end_date: str | None = None
    end_time: str | None = None
    # we still keep UTC internally but don't need to show it if you don't want
    status: str
    notes: str | None = None
    pay_total: float | None = None
