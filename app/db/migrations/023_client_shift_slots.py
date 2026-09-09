"""
Migration 023: Create client_shift_slots table and seed default slots for existing clients.
Each client gets 3 default shift slots: Morning (DAY), Afternoon (DAY), Night (NIGHT).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from app.db.session import SessionLocal
from sqlalchemy import text

DEFAULT_SLOTS = [
    ("Morning",   "07:00", "15:00", "DAY",   0),
    ("Afternoon", "15:00", "23:00", "DAY",   1),
    ("Night",     "23:00", "07:00", "NIGHT", 2),
]

def run():
    db = SessionLocal()
    try:
        # Create table
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS client_shift_slots (
                slot_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id  INTEGER NOT NULL REFERENCES clients(client_id),
                slot_name  TEXT    NOT NULL,
                start_time TEXT    NOT NULL,
                end_time   TEXT    NOT NULL,
                rate_type  TEXT    NOT NULL DEFAULT 'DAY',
                sort_order INTEGER NOT NULL DEFAULT 0
            )
        """))
        db.commit()
        print("Table client_shift_slots created (or already exists).")

        # Seed default slots for clients that have none
        client_ids = [row[0] for row in db.execute(text("SELECT client_id FROM clients")).fetchall()]
        seeded = 0
        for cid in client_ids:
            existing = db.execute(
                text("SELECT COUNT(*) FROM client_shift_slots WHERE client_id = :cid"),
                {"cid": cid}
            ).scalar()
            if existing == 0:
                for name, st, et, rt, so in DEFAULT_SLOTS:
                    db.execute(text("""
                        INSERT INTO client_shift_slots (client_id, slot_name, start_time, end_time, rate_type, sort_order)
                        VALUES (:cid, :name, :st, :et, :rt, :so)
                    """), {"cid": cid, "name": name, "st": st, "et": et, "rt": rt, "so": so})
                seeded += 1
        db.commit()
        print(f"Default slots seeded for {seeded} client(s).")
    finally:
        db.close()

if __name__ == "__main__":
    run()
