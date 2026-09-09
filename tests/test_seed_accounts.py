import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import init_seed
from app.models.tables import Base, User
from app.core.security import verify_password


class SeedAccountsTests(unittest.TestCase):
    def test_seed_adds_default_accounts_when_other_users_exist(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        with patch.object(init_seed, "SessionLocal", SessionLocal):
            with SessionLocal() as db:
                db.add(User(email="someone@example.com", password_hash="x", role="ADMIN", status="ACTIVE", must_change_password=0))
                db.commit()

            init_seed.seed()

            with SessionLocal() as db:
                admin = db.query(User).filter(User.email == "admin@test.com").first()
                caregiver = db.query(User).filter(User.email == "care1@test.com").first()

                self.assertIsNotNone(admin)
                self.assertTrue(verify_password("admin123", admin.password_hash))
                self.assertIsNotNone(caregiver)
                self.assertTrue(verify_password("test123", caregiver.password_hash))


if __name__ == "__main__":
    unittest.main()
