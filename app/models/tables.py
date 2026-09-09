from sqlalchemy.orm import declarative_base, relationship, Mapped, mapped_column
from sqlalchemy import Integer, String, Text, ForeignKey, Numeric, UniqueConstraint, CheckConstraint, Float


Base = declarative_base()

# -----------------------
# Auth / Users
# -----------------------
class User(Base):
    __tablename__ = "users"
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)   # ADMIN / CAREGIVER
    status: Mapped[str] = mapped_column(String, nullable=False) # ACTIVE / INACTIVE
    must_change_password: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    client_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    caregiver = relationship("Caregiver", back_populates="user", uselist=False)

# -----------------------
# Caregivers & Clients
# -----------------------
class Caregiver(Base):
    __tablename__ = "caregivers"
    caregiver_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id"), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    phone: Mapped[str | None]
    address: Mapped[str | None]
    active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    user = relationship("User", back_populates="caregiver")
    shifts = relationship("Shift", back_populates="caregiver")
    client_rates = relationship("CaregiverClientRate", back_populates="caregiver", cascade="all, delete-orphan")


class Client(Base):
    __tablename__ = "clients"
    client_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None]
    phone: Mapped[str | None]
    address: Mapped[str | None]
    active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # billing rates (already added earlier)
    bill_day: Mapped[float | None]
    bill_night: Mapped[float | None]

    # caregiver pay rates and day/night schedule
    pay_day: Mapped[float | None]
    pay_night: Mapped[float | None]
    day_window_start: Mapped[str | None]  # "HH:MM"
    day_window_end: Mapped[str | None]    # "HH:MM"

    # NEW: invoice cycle settings
    invoice_cycle: Mapped[str | None]      # e.g., "WEEKLY"
    invoice_anchor_dow: Mapped[int | None] # 0=Mon ... 6=Sun (default 6)
    invoice_anchor_time: Mapped[str | None]# "HH:MM" (default "23:00")
    timezone: Mapped[str | None]           # defaults to settings.TIMEZONE if null
    
    holiday_bill_multiplier: Mapped[float | None]
    holiday_pay_multiplier:  Mapped[float | None]
    caregiver_rates = relationship("CaregiverClientRate", back_populates="client", cascade="all, delete-orphan")
    shift_slots = relationship("ClientShiftSlot", back_populates="client", cascade="all, delete-orphan", order_by="ClientShiftSlot.sort_order")


class ClientShiftSlot(Base):
    __tablename__ = "client_shift_slots"
    slot_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("clients.client_id"), nullable=False)
    slot_name: Mapped[str] = mapped_column(String, nullable=False)   # e.g. "Morning"
    start_time: Mapped[str] = mapped_column(String, nullable=False)  # "HH:MM"
    end_time: Mapped[str] = mapped_column(String, nullable=False)    # "HH:MM"
    rate_type: Mapped[str] = mapped_column(String, nullable=False, default="DAY")  # DAY | NIGHT
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    client = relationship("Client", back_populates="shift_slots")


class ScheduleAssignment(Base):
    __tablename__ = "schedule_assignments"
    __table_args__ = (
        UniqueConstraint("client_id", "slot_id", "assign_date", name="uq_assignment_slot_date"),
    )
    assignment_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("clients.client_id"), nullable=False)
    slot_id: Mapped[int] = mapped_column(Integer, ForeignKey("client_shift_slots.slot_id"), nullable=False)
    caregiver_id: Mapped[int] = mapped_column(Integer, ForeignKey("caregivers.caregiver_id"), nullable=False)
    assign_date: Mapped[str] = mapped_column(String, nullable=False)   # "YYYY-MM-DD"

    client = relationship("Client")
    slot = relationship("ClientShiftSlot")
    caregiver = relationship("Caregiver")


class CaregiverClientRate(Base):
    __tablename__ = "caregiver_client_rates"
    __table_args__ = (
        UniqueConstraint("caregiver_id", "client_id", name="uq_caregiver_client_rate"),
    )

    rate_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    caregiver_id: Mapped[int] = mapped_column(Integer, ForeignKey("caregivers.caregiver_id"), nullable=False)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("clients.client_id"), nullable=False)
    pay_day: Mapped[float] = mapped_column(Numeric, nullable=False, default=0)
    pay_night: Mapped[float] = mapped_column(Numeric, nullable=False, default=0)
    is_custom: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    caregiver = relationship("Caregiver", back_populates="client_rates")
    client = relationship("Client", back_populates="caregiver_rates")


# -----------------------
# Pay rules (optional; kept from your file)
# -----------------------
class PayRule(Base):
    __tablename__ = "pay_rules"
    pay_rule_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("clients.client_id"), nullable=False)
    rule_name: Mapped[str] = mapped_column(String, nullable=False)
    rate_day: Mapped[float] = mapped_column(Numeric, nullable=False)
    rate_night: Mapped[float] = mapped_column(Numeric, nullable=False)
    day_window_start: Mapped[str] = mapped_column(String, nullable=False)  # "HH:MM"
    day_window_end: Mapped[str] = mapped_column(String, nullable=False)    # "HH:MM"
    overtime_after_hours: Mapped[float | None]
    overtime_multiplier: Mapped[float | None]
    effective_start: Mapped[str] = mapped_column(String, nullable=False)   # "YYYY-MM-DD"
    effective_end: Mapped[str | None]

# -----------------------
# Shifts + Calculations
# -----------------------
class Shift(Base):
    __tablename__ = "shifts"
    shift_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("clients.client_id"), nullable=False)
    caregiver_id: Mapped[int] = mapped_column(Integer, ForeignKey("caregivers.caregiver_id"), nullable=False)

    # Local display fields
    start_date: Mapped[str | None] = mapped_column(String, nullable=True)
    start_time: Mapped[str | None] = mapped_column(String, nullable=True)
    end_date:   Mapped[str | None] = mapped_column(String, nullable=True)
    end_time:   Mapped[str | None] = mapped_column(String, nullable=True)

    # UTC audit fields
    check_in_ts: Mapped[str] = mapped_column(String, nullable=False)      # UTC ISO
    check_out_ts: Mapped[str | None] = mapped_column(String, nullable=True)

    status: Mapped[str] = mapped_column(String, nullable=False)           # OPEN/CLOSED/VOID
    notes: Mapped[str | None]
    created_by: Mapped[int | None]
    updated_by: Mapped[int | None]
    created_at: Mapped[str]
    updated_at: Mapped[str]

    caregiver = relationship("Caregiver", back_populates="shifts")
    calc = relationship("ShiftCalc", back_populates="shift", uselist=False)

class ShiftCalc(Base):
    __tablename__ = "shift_calcs"
    shift_id: Mapped[int] = mapped_column(Integer, ForeignKey("shifts.shift_id"), primary_key=True)
    hours_total: Mapped[float]
    hours_day: Mapped[float]
    hours_night: Mapped[float]
    hours_overtime: Mapped[float]
    pay_day: Mapped[float]
    pay_night: Mapped[float]
    pay_overtime: Mapped[float]
    pay_total: Mapped[float]
    pay_rule_id: Mapped[int] = mapped_column(Integer, ForeignKey("pay_rules.pay_rule_id"))
    calc_version: Mapped[int]
    calculated_at: Mapped[str]

    shift = relationship("Shift", back_populates="calc")

# -----------------------
# Invoices (FINAL schema used by API)
# -----------------------
class Invoice(Base):
    __tablename__ = "invoices"
    invoice_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("clients.client_id"), nullable=False)
    from_utc: Mapped[str] = mapped_column(String, nullable=False)   # ISO string
    to_utc:   Mapped[str] = mapped_column(String, nullable=False)   # ISO string
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)

    # NEW: lifecycle status (DRAFT, FINALIZED, PAID, VOID)
    status: Mapped[str] = mapped_column(String, nullable=False, default="DRAFT")

    client = relationship("Client")
    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")

    
class InvoiceItem(Base):
    __tablename__ = "invoice_items"
    item_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(Integer, ForeignKey("invoices.invoice_id"), nullable=False)
    shift_id: Mapped[int] = mapped_column(Integer, ForeignKey("shifts.shift_id"), nullable=False)
    desc: Mapped[str] = mapped_column(String, nullable=False)  # e.g., "2025-11-23 09:00–17:30"
    hours_day: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    hours_night: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rate_day: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rate_night: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    invoice = relationship("Invoice", back_populates="items")
    shift = relationship("Shift")


class Holiday(Base):
    __tablename__ = "holidays"

    holiday_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("clients.client_id"), nullable=True)
    date: Mapped[str] = mapped_column(String, nullable=False)    # YYYY-MM-DD local
    name: Mapped[str] = mapped_column(String, nullable=False)
    multiplier_bill: Mapped[float | None] = mapped_column(Float, nullable=True)
    multiplier_pay: Mapped[float | None] = mapped_column(Float, nullable=True)

