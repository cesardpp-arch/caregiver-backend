import sqlite3
from app.core.config import settings
DB = settings.DATABASE_PATH

def col_exists(cur, table, col):
    cur.execute(f"PRAGMA table_info({table});")
    return any(r[1] == col for r in cur.fetchall())

def main():
    conn = sqlite3.connect(DB); cur = conn.cursor()
    try:
        if not col_exists(cur, "clients", "holiday_bill_multiplier"):
            cur.execute("ALTER TABLE clients ADD COLUMN holiday_bill_multiplier REAL;")
        if not col_exists(cur, "clients", "holiday_pay_multiplier"):
            cur.execute("ALTER TABLE clients ADD COLUMN holiday_pay_multiplier REAL;")
        conn.commit()
        cur.execute("""
            UPDATE clients
            SET holiday_bill_multiplier = COALESCE(holiday_bill_multiplier, 1.0),
                holiday_pay_multiplier  = COALESCE(holiday_pay_multiplier,  1.0)
        """)
        conn.commit()
        print("010: clients holiday multipliers ready (default 1.0).")
    finally:
        cur.close(); conn.close()

if __name__ == "__main__":
    main()
