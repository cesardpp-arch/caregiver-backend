import sqlite3
from app.core.config import settings

DB = settings.DATABASE_PATH

def col_exists(cur, table, col):
    cur.execute(f"PRAGMA table_info({table});")
    return any(r[1] == col for r in cur.fetchall())

def main():
    print("DB:", DB)
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    try:
        # invoice_cycle: e.g., "WEEKLY" (default)
        if not col_exists(cur, "clients", "invoice_cycle"):
            cur.execute("ALTER TABLE clients ADD COLUMN invoice_cycle TEXT;")
            print("Added clients.invoice_cycle")

        # invoice_anchor_dow: 0=Mon ... 6=Sun (default 6 for Sunday)
        if not col_exists(cur, "clients", "invoice_anchor_dow"):
            cur.execute("ALTER TABLE clients ADD COLUMN invoice_anchor_dow INTEGER;")
            print("Added clients.invoice_anchor_dow")

        # invoice_anchor_time: "HH:MM" (default "23:00")
        if not col_exists(cur, "clients", "invoice_anchor_time"):
            cur.execute("ALTER TABLE clients ADD COLUMN invoice_anchor_time TEXT;")
            print("Added clients.invoice_anchor_time")

        # optional: per-client timezone (falls back to settings.TIMEZONE if null)
        if not col_exists(cur, "clients", "timezone"):
            cur.execute("ALTER TABLE clients ADD COLUMN timezone TEXT;")
            print("Added clients.timezone")

        conn.commit()

        # Initialize reasonable defaults where null
        cur.execute("""
            UPDATE clients
            SET invoice_cycle = COALESCE(invoice_cycle, 'WEEKLY'),
                invoice_anchor_dow = COALESCE(invoice_anchor_dow, 6),
                invoice_anchor_time = COALESCE(invoice_anchor_time, '23:00'),
                timezone = COALESCE(timezone, ?)
        """, (settings.TIMEZONE,))
        conn.commit()

        print("Migration 007 complete.")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()
