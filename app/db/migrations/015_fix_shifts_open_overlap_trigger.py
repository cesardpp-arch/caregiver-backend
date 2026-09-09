import sqlite3

DB_PATH = r"C:\Shana\caregiver-system\data\caregiver.db"

SQL_DROP_INSERT = "DROP TRIGGER IF EXISTS trg_shifts_no_overlap_ins;"
SQL_DROP_UPDATE = "DROP TRIGGER IF EXISTS trg_shifts_no_overlap_upd;"

SQL_BEFORE_INSERT = """
CREATE TRIGGER trg_shifts_no_overlap_ins
BEFORE INSERT ON shifts
BEGIN
    -- end must be > start when end is provided
    SELECT CASE
      WHEN NEW.check_out_ts IS NOT NULL AND NEW.check_out_ts <= NEW.check_in_ts
      THEN RAISE(ABORT, 'Shift end must be after start')
    END;

    -- overlap rules:
    -- 1) OPEN check-in (NEW.check_out_ts IS NULL): only block if another shift is active at NEW.check_in_ts
    -- 2) CLOSED insert: block on real interval overlap
    SELECT CASE
      WHEN EXISTS (
        SELECT 1
        FROM shifts s
        WHERE s.caregiver_id = NEW.caregiver_id
          AND s.status != 'VOID'
          AND (
            (
              NEW.check_out_ts IS NULL
              AND s.check_in_ts <= NEW.check_in_ts
              AND COALESCE(s.check_out_ts, '9999-12-31T00:00:00Z') > NEW.check_in_ts
            )
            OR
            (
              NEW.check_out_ts IS NOT NULL
              AND s.check_in_ts < NEW.check_out_ts
              AND COALESCE(s.check_out_ts, '9999-12-31T00:00:00Z') > NEW.check_in_ts
            )
          )
      )
      THEN RAISE(ABORT, 'Caregiver overlap with another shift')
    END;
END;
"""

SQL_BEFORE_UPDATE = """
CREATE TRIGGER trg_shifts_no_overlap_upd
BEFORE UPDATE ON shifts
BEGIN
    -- end must be > start when end is provided
    SELECT CASE
      WHEN NEW.check_out_ts IS NOT NULL AND NEW.check_out_ts <= NEW.check_in_ts
      THEN RAISE(ABORT, 'Shift end must be after start')
    END;

    -- overlap rules, excluding self row on update
    SELECT CASE
      WHEN EXISTS (
        SELECT 1
        FROM shifts s
        WHERE s.caregiver_id = NEW.caregiver_id
          AND s.shift_id != NEW.shift_id
          AND s.status != 'VOID'
          AND (
            (
              NEW.check_out_ts IS NULL
              AND s.check_in_ts <= NEW.check_in_ts
              AND COALESCE(s.check_out_ts, '9999-12-31T00:00:00Z') > NEW.check_in_ts
            )
            OR
            (
              NEW.check_out_ts IS NOT NULL
              AND s.check_in_ts < NEW.check_out_ts
              AND COALESCE(s.check_out_ts, '9999-12-31T00:00:00Z') > NEW.check_in_ts
            )
          )
      )
      THEN RAISE(ABORT, 'Caregiver overlap with another shift')
    END;
END;
"""


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute(SQL_DROP_INSERT)
        cur.execute(SQL_DROP_UPDATE)
        cur.execute(SQL_BEFORE_INSERT)
        cur.execute(SQL_BEFORE_UPDATE)
        conn.commit()
        print("Migration 015 complete: fixed open-shift overlap guardrails.")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
