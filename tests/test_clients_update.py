import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1.clients import ClientUpdate, update_client
from app.models.tables import Base, Caregiver, Client, Shift, User


class ClientUpdateTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        self.db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()

        user = User(email="cg@example.com", password_hash="x", role="CAREGIVER", status="ACTIVE", must_change_password=0)
        self.db.add(user)
        self.db.flush()
        client = Client(name="Client", bill_day=20.0, bill_night=15.0, active=1,
                        day_window_start="07:00", day_window_end="23:00")
        self.db.add(client)
        self.db.flush()
        caregiver = Caregiver(user_id=user.user_id, name="Caregiver", active=1)
        self.db.add(caregiver)
        self.db.flush()
        # Closed shift for a caregiver with no pay rate configured for this client.
        self.db.add(Shift(
            client_id=client.client_id, caregiver_id=caregiver.caregiver_id,
            start_date="2026-06-08", start_time="15:00", end_date="2026-06-08", end_time="23:00",
            check_in_ts="2026-06-08T15:00:00+00:00", check_out_ts="2026-06-08T23:00:00+00:00",
            status="CLOSED", notes="", created_at="2026-06-08T00:00:00+00:00", updated_at="2026-06-08T00:00:00+00:00",
        ))
        self.db.commit()
        self.client_id = client.client_id

    def tearDown(self):
        self.db.close()

    def test_changing_bill_rates_with_same_window_saves(self):
        payload = ClientUpdate(bill_day=35.0, bill_night=25.0, day_window_start="07:00", day_window_end="23:00")
        result = update_client(self.client_id, payload, db=self.db, _=object())
        self.assertEqual(result["bill_day"], 35.0)
        self.assertEqual(result["bill_night"], 25.0)

    def test_changing_window_with_missing_pay_rate_returns_clear_error(self):
        payload = ClientUpdate(day_window_start="06:00")
        with self.assertRaises(HTTPException) as ctx:
            update_client(self.client_id, payload, db=self.db, _=object())
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("No pay rate configured", ctx.exception.detail)
        self.assertEqual(self.db.get(Client, self.client_id).day_window_start, "07:00")


if __name__ == "__main__":
    unittest.main()
