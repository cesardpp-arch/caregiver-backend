import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1.invoices import calculate_invoice_number, create_invoice_from_report, invoice_detail, list_invoices
from app.models.tables import Base, User, Caregiver, Client, Shift, ShiftCalc, PayRule, Invoice, InvoiceItem


class InvoiceGenerationTests(unittest.TestCase):
    def test_calculate_invoice_number_uses_week_anchor(self):
        self.assertEqual(calculate_invoice_number("2026-01-05"), 1)
        self.assertEqual(calculate_invoice_number("2026-07-26"), 30)
        self.assertEqual(calculate_invoice_number("2026-08-02"), 31)

    def test_create_invoice_from_report_persists_invoice_and_items(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        with SessionLocal() as db:
            user = User(email="caregiver@example.com", password_hash="x", role="CAREGIVER", status="ACTIVE", must_change_password=0)
            db.add(user)
            db.flush()

            client = Client(name="Test Client", bill_day=20.0, bill_night=15.0, active=1)
            db.add(client)
            db.flush()

            caregiver = Caregiver(user_id=user.user_id, name="Test Caregiver", active=1)
            db.add(caregiver)
            db.flush()

            pay_rule = PayRule(client_id=client.client_id, rule_name="Default", rate_day=20.0, rate_night=15.0, day_window_start="07:00", day_window_end="23:00", effective_start="2024-01-01")
            db.add(pay_rule)
            db.flush()

            shift = Shift(
                client_id=client.client_id,
                caregiver_id=caregiver.caregiver_id,
                start_date="2024-01-01",
                start_time="08:00",
                end_date="2024-01-01",
                end_time="16:00",
                check_in_ts="2024-01-01T08:00:00+00:00",
                check_out_ts="2024-01-01T16:00:00+00:00",
                status="CLOSED",
                notes="",
                created_at="2024-01-01T00:00:00+00:00",
                updated_at="2024-01-01T00:00:00+00:00",
            )
            db.add(shift)
            db.flush()

            shift_calc = ShiftCalc(
                shift_id=shift.shift_id,
                hours_total=8.0,
                hours_day=8.0,
                hours_night=0.0,
                hours_overtime=0.0,
                pay_day=160.0,
                pay_night=0.0,
                pay_overtime=0.0,
                pay_total=160.0,
                pay_rule_id=pay_rule.pay_rule_id,
                calc_version=1,
                calculated_at="2024-01-01T00:00:00+00:00",
            )
            db.add(shift_calc)
            db.commit()

            result = create_invoice_from_report(
                client_id=client.client_id,
                from_date="2024-01-01",
                from_time="00:00",
                to_date="2024-01-01",
                to_time="23:59",
                notes="Test invoice",
                _=object(),
                db=db,
            )

            invoice = db.query(Invoice).filter(Invoice.invoice_id == result["invoice_id"]).first()
            items = db.query(InvoiceItem).filter(InvoiceItem.invoice_id == invoice.invoice_id).all()

            self.assertIsNotNone(invoice)
            self.assertEqual(invoice.client_id, client.client_id)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].shift_id, shift.shift_id)
            self.assertEqual(invoice.status, "FINALIZED")

    def test_invoice_detail_includes_caregiver_summary_and_detail_rows(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        with SessionLocal() as db:
            user = User(email="caregiver2@example.com", password_hash="x", role="CAREGIVER", status="ACTIVE", must_change_password=0)
            db.add(user)
            db.flush()

            client = Client(name="Detail Client", bill_day=20.0, bill_night=15.0, active=1)
            db.add(client)
            db.flush()

            caregiver = Caregiver(user_id=user.user_id, name="Detail Caregiver", active=1)
            db.add(caregiver)
            db.flush()

            pay_rule = PayRule(client_id=client.client_id, rule_name="Default", rate_day=20.0, rate_night=15.0, day_window_start="07:00", day_window_end="23:00", effective_start="2024-01-01")
            db.add(pay_rule)
            db.flush()

            shift = Shift(
                client_id=client.client_id,
                caregiver_id=caregiver.caregiver_id,
                start_date="2024-01-01",
                start_time="08:00",
                end_date="2024-01-01",
                end_time="16:00",
                check_in_ts="2024-01-01T08:00:00+00:00",
                check_out_ts="2024-01-01T16:00:00+00:00",
                status="CLOSED",
                notes="On site",
                created_at="2024-01-01T00:00:00+00:00",
                updated_at="2024-01-01T00:00:00+00:00",
            )
            db.add(shift)
            db.flush()

            shift_calc = ShiftCalc(
                shift_id=shift.shift_id,
                hours_total=8.0,
                hours_day=8.0,
                hours_night=0.0,
                hours_overtime=0.0,
                pay_day=160.0,
                pay_night=0.0,
                pay_overtime=0.0,
                pay_total=160.0,
                pay_rule_id=pay_rule.pay_rule_id,
                calc_version=1,
                calculated_at="2024-01-01T00:00:00+00:00",
            )
            db.add(shift_calc)
            db.commit()

            created = create_invoice_from_report(
                client_id=client.client_id,
                from_date="2024-01-01",
                from_time="00:00",
                to_date="2024-01-01",
                to_time="23:59",
                notes="Detail invoice",
                _=object(),
                db=db,
            )
            detail = invoice_detail(created["invoice_id"], _=object(), db=db)

            self.assertIn("summary_rows", detail)
            self.assertIn("detail_rows", detail)
            self.assertEqual(detail["summary_rows"][0]["caregiver_name"], "Detail Caregiver")
            self.assertEqual(detail["detail_rows"][0]["caregiver_name"], "Detail Caregiver")
            self.assertEqual(detail["detail_rows"][0]["notes"], "On site")

    def test_list_invoices_can_filter_by_client_and_date(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        with SessionLocal() as db:
            client = Client(name="Filtered Client", bill_day=10.0, bill_night=5.0, active=1)
            db.add(client)
            db.flush()

            inv = Invoice(
                client_id=client.client_id,
                from_utc="2024-01-01T00:00:00+00:00",
                to_utc="2024-01-31T23:59:59+00:00",
                created_at="2024-01-15T00:00:00+00:00",
                total_amount=12.0,
                notes="",
                status="DRAFT",
            )
            db.add(inv)
            db.commit()

            result = list_invoices(client_id=client.client_id, from_date="2024-01-01", to_date="2024-02-01", _=object(), db=db)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["invoice_id"], inv.invoice_id)
            self.assertEqual(result[0]["invoice_number"], 1)
            self.assertEqual(result[0]["from_date"], "2024-01-01")
            self.assertEqual(result[0]["to_date"], "2024-01-31")


if __name__ == "__main__":
    unittest.main()
