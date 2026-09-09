from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.tables import User, Caregiver, Client, PayRule, CaregiverClientRate
from app.core.security import hash_password
from datetime import date


def seed():
    db: Session = SessionLocal()

    admin = db.query(User).filter(User.email == "admin@test.com").first()
    if not admin:
        admin = User(
            email="admin@test.com",
            password_hash=hash_password("admin123"),
            role="ADMIN",
            status="ACTIVE",
            must_change_password=0,
        )
        db.add(admin)
        db.flush()

    cg_user = db.query(User).filter(User.email == "care1@test.com").first()
    if not cg_user:
        cg_user = User(
            email="care1@test.com",
            password_hash=hash_password("test123"),
            role="CAREGIVER",
            status="ACTIVE",
            must_change_password=1,
        )
        db.add(cg_user)
        db.flush()
    else:
        cg_user.password_hash = hash_password("test123")
        cg_user.role = "CAREGIVER"
        cg_user.status = "ACTIVE"
        cg_user.must_change_password = 1

    # Ensure the Adriana caregiver account can log in with the known demo password.
    adriana = db.query(User).filter(User.email == "adriana@gmail.com").first()
    if not adriana:
        adriana = User(
            email="adriana@gmail.com",
            password_hash=hash_password("test123"),
            role="CAREGIVER",
            status="ACTIVE",
            must_change_password=1,
        )
        db.add(adriana)
        db.flush()
    else:
        adriana.password_hash = hash_password("test123")
        adriana.role = "CAREGIVER"
        adriana.status = "ACTIVE"
        adriana.must_change_password = 1

    if db.query(Caregiver).filter(Caregiver.user_id == cg_user.user_id).first():
        caregiver = db.query(Caregiver).filter(Caregiver.user_id == cg_user.user_id).first()
    else:
        caregiver = Caregiver(
            user_id=cg_user.user_id,
            name="John Caregiver",
            phone="555-2222",
            address="123 Main St",
            active=1,
        )
        db.add(caregiver)
        db.flush()

    if db.query(Client).first():
        client = db.query(Client).first()
    else:
        client = Client(
            name="Client One",
            email="client@example.com",
            phone="555-1111",
            address="456 Park Dr",
            active=1,
            bill_day=35.00,
            bill_night=20.00,
            day_window_start="07:00",
            day_window_end="23:01",
            invoice_cycle="WEEKLY",
            invoice_anchor_dow=6,  # Sunday (Python convention: 0=Mon...6=Sun)
            invoice_anchor_time="23:00",  # 11:00 PM
            timezone="America/New_York",
            holiday_bill_multiplier=1.5,
            holiday_pay_multiplier=1.5,
        )
        db.add(client)
        db.flush()

    if not db.query(PayRule).filter(PayRule.client_id == client.client_id).first():
        pay_rule = PayRule(
            client_id=client.client_id,
            rule_name="Client Config",
            rate_day=20.00,
            rate_night=15.00,
            day_window_start="07:00",
            day_window_end="23:01",
            overtime_after_hours=None,
            overtime_multiplier=None,
            effective_start=str(date.today()),
            effective_end=None,
        )
        db.add(pay_rule)

    if not db.query(CaregiverClientRate).filter(CaregiverClientRate.caregiver_id == caregiver.caregiver_id, CaregiverClientRate.client_id == client.client_id).first():
        db.add(CaregiverClientRate(
            caregiver_id=caregiver.caregiver_id,
            client_id=client.client_id,
            pay_day=20.00,
            pay_night=15.00,
            is_custom=1,
        ))

    db.commit()
    print("SEED COMPLETE.")


if __name__ == "__main__":
    seed()

    # ---- Caregiver profile
    caregiver = Caregiver(
        user_id=cg_user.user_id,
        name="John Caregiver",
        phone="555-2222",
        address="123 Main St",
        active=1,
    )
    db.add(caregiver)
    db.flush()

    # ---- Client
    client = Client(
        name="Client One",
        email="client@example.com",
        phone="555-1111",
        address="456 Park Dr",
        active=1,
        bill_day=35.00,
        bill_night=20.00,
        day_window_start="07:00",
        day_window_end="23:01",
        invoice_cycle="WEEKLY",
        invoice_anchor_dow=6,  # Sunday (Python convention: 0=Mon...6=Sun)
        invoice_anchor_time="23:00",  # 11:00 PM
        timezone="America/New_York",
        holiday_bill_multiplier=1.5,
        holiday_pay_multiplier=1.5,
    )
    db.add(client)
    db.flush()

    # ---- Pay Rule (effective today)
    pay_rule = PayRule(
        client_id=client.client_id,
        rule_name="Client Config",
        rate_day=20.00,
        rate_night=15.00,
        day_window_start="07:00",
        day_window_end="23:01",
        overtime_after_hours=None,
        overtime_multiplier=None,
        effective_start=str(date.today()),
        effective_end=None,
    )
    db.add(pay_rule)

    db.add(CaregiverClientRate(
        caregiver_id=caregiver.caregiver_id,
        client_id=client.client_id,
        pay_day=20.00,
        pay_night=15.00,
        is_custom=1,
    ))

    db.commit()
    print("SEED COMPLETE.")


if __name__ == "__main__":
    seed()
