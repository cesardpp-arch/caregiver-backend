"""
Migration 024: Create schedule_assignments table.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from app.db.session import SessionLocal
from sqlalchemy import text

def run():
    db = SessionLocal()
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS schedule_assignments (
                assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id     INTEGER NOT NULL REFERENCES clients(client_id),
                slot_id       INTEGER NOT NULL REFERENCES client_shift_slots(slot_id),
                caregiver_id  INTEGER NOT NULL REFERENCES caregivers(caregiver_id),
                assign_date   TEXT    NOT NULL,
                UNIQUE(client_id, slot_id, assign_date)
            )
        """))
        db.commit()
        print("Table schedule_assignments created.")
    finally:
        db.close()

if __name__ == "__main__":
    run()
