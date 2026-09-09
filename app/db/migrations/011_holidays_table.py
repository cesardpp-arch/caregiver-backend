import sqlite3
from app.core.config import settings
DB = settings.DATABASE_PATH

def main():
    conn = sqlite3.connect(DB); cur = conn.cursor()
    try:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS holidays (
          holiday_id INTEGER PRIMARY KEY,
          client_id  INTEGER,            -- NULL = global
          date       TEXT NOT NULL,      -- 'YYYY-MM-DD' (local date in client's tz)
          name       TEXT NOT NULL,
          multiplier_bill REAL,          -- NULL => use client's default
          multiplier_pay  REAL,          -- NULL => use client's default
          UNIQUE(client_id, date, name)
        );
        """)
        conn.commit()
        print("011: holidays table ready.")
    finally:
        cur.close(); conn.close()

if __name__ == "__main__":
    main()
