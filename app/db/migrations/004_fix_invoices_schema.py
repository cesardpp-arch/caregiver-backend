# Fix invoices schema if it's still the legacy version (no from_utc / to_utc).
import sqlite3
from app.core.config import settings

DB_PATH = settings.DATABASE_PATH  # we set this in config.py

INVOICES_SQL = """
CREATE TABLE IF NOT EXISTS invoices (
    invoice_id    INTEGER PRIMARY KEY,
    client_id     INTEGER NOT NULL,
    from_utc      TEXT    NOT NULL,
    to_utc        TEXT    NOT NULL,
    created_at    TEXT    NOT NULL,
    total_amount  REAL    NOT NULL DEFAULT 0.0,
    notes         TEXT,
    FOREIGN KEY(client_id) REFERENCES clients(client_id)
);
"""

INVOICE_ITEMS_SQL = """
CREATE TABLE IF NOT EXISTS invoice_items (
    item_id     INTEGER PRIMARY KEY,
    invoice_id  INTEGER NOT NULL,
    shift_id    INTEGER NOT NULL,
    desc        TEXT    NOT NULL,
    hours_day   REAL    NOT NULL DEFAULT 0.0,
    hours_night REAL    NOT NULL DEFAULT 0.0,
    rate_day    REAL    NOT NULL DEFAULT 0.0,
    rate_night  REAL    NOT NULL DEFAULT 0.0,
    amount      REAL    NOT NULL DEFAULT 0.0,
    FOREIGN KEY(invoice_id) REFERENCES invoices(invoice_id),
    FOREIGN KEY(shift_id)   REFERENCES shifts(shift_id)
);
"""

UNIQUE_INDEX_SQL = "CREATE UNIQUE INDEX IF NOT EXISTS ux_invoice_items_shift ON invoice_items(shift_id);"

def table_exists(cur, name: str) -> bool:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (name,))
    return cur.fetchone() is not None

def has_column(cur, table: str, col: str) -> bool:
    cur.execute(f"PRAGMA table_info({table});")
    return any(r[1] == col for r in cur.fetchall())

def main():
    print("DB PATH:", DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        # If invoices table doesn't exist at all, just create the correct one.
        if not table_exists(cur, "invoices"):
            print("invoices table not found -> creating new schema")
            cur.execute(INVOICES_SQL)
            conn.commit()
        else:
            # If it exists but lacks from_utc, it's the legacy schema. Rename & recreate.
            if not has_column(cur, "invoices", "from_utc"):
                print("Legacy invoices schema detected (no from_utc) -> renaming to invoices_legacy")
                cur.execute("ALTER TABLE invoices RENAME TO invoices_legacy;")
                cur.execute(INVOICES_SQL)
                conn.commit()
            else:
                print("invoices schema already OK")

        # Ensure invoice_items exists with the correct columns
        if not table_exists(cur, "invoice_items"):
            print("invoice_items not found -> creating")
            cur.execute(INVOICE_ITEMS_SQL)
            conn.commit()
        else:
            # If legacy invoice_items exists, we won't try to auto-migrate columns here.
            print("invoice_items table exists (assuming OK).")

        # Ensure unique index to prevent double-billing a shift
        cur.execute(UNIQUE_INDEX_SQL)
        conn.commit()

        print("Migration 004 complete.")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()
