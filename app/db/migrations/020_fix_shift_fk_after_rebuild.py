import sqlite3

DB_PATH = r"C:\Shana\caregiver-system\data\caregiver.db"

SQL_CREATE_SHIFT_CALCS = """
CREATE TABLE shift_calcs (
  shift_id       INTEGER PRIMARY KEY,
  hours_total    NUMERIC NOT NULL,
  hours_day      NUMERIC NOT NULL,
  hours_night    NUMERIC NOT NULL,
  hours_overtime NUMERIC NOT NULL DEFAULT 0,
  pay_day        NUMERIC NOT NULL,
  pay_night      NUMERIC NOT NULL,
  pay_overtime   NUMERIC NOT NULL DEFAULT 0,
  pay_total      NUMERIC NOT NULL,
  pay_rule_id    INTEGER NOT NULL,
  calc_version   INTEGER NOT NULL DEFAULT 1,
  calculated_at  TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (shift_id) REFERENCES shifts(shift_id) ON DELETE CASCADE,
  FOREIGN KEY (pay_rule_id) REFERENCES pay_rules(pay_rule_id)
);
"""

SQL_CREATE_INVOICE_ITEMS = """
CREATE TABLE invoice_items (
    item_id      INTEGER PRIMARY KEY,
    invoice_id   INTEGER NOT NULL,
    shift_id     INTEGER NOT NULL,
    "desc"       TEXT NOT NULL,
    hours_day    REAL NOT NULL DEFAULT 0.0,
    hours_night  REAL NOT NULL DEFAULT 0.0,
    rate_day     REAL NOT NULL DEFAULT 0.0,
    rate_night   REAL NOT NULL DEFAULT 0.0,
    amount       REAL NOT NULL DEFAULT 0.0,
    FOREIGN KEY(invoice_id) REFERENCES invoices(invoice_id),
    FOREIGN KEY(shift_id) REFERENCES shifts(shift_id)
);
"""


def table_exists(cur, table: str) -> bool:
    row = cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return bool(row)


def fk_targets(cur, table: str) -> set[str]:
    return {row[2] for row in cur.execute(f"PRAGMA foreign_key_list({table})").fetchall()}


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    needs_shift_calcs = table_exists(cur, "shift_calcs") and "shifts_fix_old" in fk_targets(cur, "shift_calcs")
    needs_invoice_items = table_exists(cur, "invoice_items") and "shifts_fix_old" in fk_targets(cur, "invoice_items")

    if not (needs_shift_calcs or needs_invoice_items):
        print("Migration 020 skipped: no shifts_fix_old foreign keys found")
        conn.close()
        return

    cur.execute("PRAGMA foreign_keys = OFF;")
    conn.commit()

    try:
        cur.execute("BEGIN;")

        if needs_shift_calcs:
            cur.execute("ALTER TABLE shift_calcs RENAME TO shift_calcs_fix_old;")
            cur.execute(SQL_CREATE_SHIFT_CALCS)
            cur.execute(
                """
                INSERT INTO shift_calcs (
                    shift_id, hours_total, hours_day, hours_night, hours_overtime,
                    pay_day, pay_night, pay_overtime, pay_total,
                    pay_rule_id, calc_version, calculated_at
                )
                SELECT
                    shift_id, hours_total, hours_day, hours_night, hours_overtime,
                    pay_day, pay_night, pay_overtime, pay_total,
                    pay_rule_id, calc_version, calculated_at
                FROM shift_calcs_fix_old;
                """
            )
            cur.execute("DROP TABLE shift_calcs_fix_old;")

        if needs_invoice_items:
            cur.execute("ALTER TABLE invoice_items RENAME TO invoice_items_fix_old;")
            cur.execute(SQL_CREATE_INVOICE_ITEMS)
            cur.execute(
                """
                INSERT INTO invoice_items (
                    item_id, invoice_id, shift_id, "desc", hours_day,
                    hours_night, rate_day, rate_night, amount
                )
                SELECT
                    item_id, invoice_id, shift_id, "desc", hours_day,
                    hours_night, rate_day, rate_night, amount
                FROM invoice_items_fix_old;
                """
            )
            cur.execute("DROP TABLE invoice_items_fix_old;")

        cur.execute("COMMIT;")
        print("Migration 020 complete: fixed foreign keys from shifts_fix_old to shifts")
    except Exception:
        cur.execute("ROLLBACK;")
        raise
    finally:
        cur.execute("PRAGMA foreign_keys = ON;")
        conn.commit()
        conn.close()


if __name__ == "__main__":
    main()
