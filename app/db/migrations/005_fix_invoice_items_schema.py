# Ensures invoice_items has the modern schema our code uses.
# If legacy schema is detected (e.g., no "desc" column), we rename & rebuild, then copy data safely.

import sqlite3
from app.core.config import settings

DB_PATH = settings.DATABASE_PATH  # comes from config; points to your real DB

REQUIRED_COLUMNS = {
    "item_id",
    "invoice_id",
    "shift_id",
    "desc",
    "hours_day",
    "hours_night",
    "rate_day",
    "rate_night",
    "amount",
}

CREATE_NEW_SQL = """
CREATE TABLE IF NOT EXISTS invoice_items (
    item_id     INTEGER PRIMARY KEY,
    invoice_id  INTEGER NOT NULL,
    shift_id    INTEGER NOT NULL,
    "desc"      TEXT    NOT NULL,
    hours_day   REAL    NOT NULL DEFAULT 0.0,
    hours_night REAL    NOT NULL DEFAULT 0.0,
    rate_day    REAL    NOT NULL DEFAULT 0.0,
    rate_night  REAL    NOT NULL DEFAULT 0.0,
    amount      REAL    NOT NULL DEFAULT 0.0,
    FOREIGN KEY(invoice_id) REFERENCES invoices(invoice_id),
    FOREIGN KEY(shift_id)   REFERENCES shifts(shift_id)
);
"""

CREATE_UNIQUE_IDX = 'CREATE UNIQUE INDEX IF NOT EXISTS ux_invoice_items_shift ON invoice_items(shift_id);'

def table_exists(cur, name):
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?;", (name,))
    return cur.fetchone() is not None

def get_columns(cur, table):
    cur.execute(f"PRAGMA table_info({table});")
    # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
    return {row[1] for row in cur.fetchall()}

def has_modern_schema(cur):
    if not table_exists(cur, "invoice_items"):
        return False
    cols = get_columns(cur, "invoice_items")
    return REQUIRED_COLUMNS.issubset(cols)

def legacy_copy_columns(cur):
    """
    Returns tuple (has_description, has_amount) to guide copy from legacy.
    """
    legacy_cols = get_columns(cur, "invoice_items_legacy")
    return ("description" in legacy_cols, "amount" in legacy_cols)

def main():
    print("Using DB:", DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        if not table_exists(cur, "invoice_items"):
            print("invoice_items: not found -> creating modern schema")
            cur.execute(CREATE_NEW_SQL)
            conn.commit()
        else:
            if has_modern_schema(cur):
                print("invoice_items: already modern schema -> nothing to do")
            else:
                print("invoice_items: legacy schema detected -> renaming and rebuilding")
                cur.execute("ALTER TABLE invoice_items RENAME TO invoice_items_legacy;")
                cur.execute(CREATE_NEW_SQL)
                conn.commit()

                # Attempt best-effort copy from legacy.
                # Map legacy `description` -> modern `"desc"`, set other fields to 0 if absent.
                has_desc_col, has_amount_col = legacy_copy_columns(cur)

                # Build INSERT ... SELECT with what we can map
                # We'll always copy invoice_id, shift_id if they exist.
                legacy_cols = get_columns(cur, "invoice_items_legacy")
                if "invoice_id" not in legacy_cols or "shift_id" not in legacy_cols:
                    print("Legacy invoice_items missing essential columns; skipping data copy.")
                else:
                    desc_expr = "description" if has_desc_col else "''"
                    amount_expr = "amount" if has_amount_col else "0.0"

                    copy_sql = f"""
                    INSERT INTO invoice_items (invoice_id, shift_id, "desc", hours_day, hours_night, rate_day, rate_night, amount)
                    SELECT invoice_id,
                           shift_id,
                           {desc_expr}             AS "desc",
                           0.0                     AS hours_day,
                           0.0                     AS hours_night,
                           0.0                     AS rate_day,
                           0.0                     AS rate_night,
                           {amount_expr}           AS amount
                    FROM invoice_items_legacy;
                    """
                    cur.execute(copy_sql)
                    conn.commit()
                    print("Copied legacy invoice_items rows into modern schema.")

        # Ensure unique index for anti double-billing
        cur.execute(CREATE_UNIQUE_IDX)
        conn.commit()

        print("Migration 005 complete.")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()
