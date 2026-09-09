import sqlite3
from app.core.config import settings

DB = settings.DATABASE_PATH

SQL_BEFORE_INSERT = """
CREATE TRIGGER IF NOT EXISTS trg_shifts_no_overlap_ins
BEFORE INSERT ON shifts
BEGIN
    -- end must be > start
    SELECT CASE
      WHEN NEW.check_out_ts IS NOT NULL AND NEW.check_out_ts <= NEW.check_in_ts
      THEN RAISE(ABORT, 'Shift end must be after start')
    END;

    -- caregiver cannot overlap own OPEN/CLOSED shifts (except VOID)
    SELECT CASE
      WHEN EXISTS (
        SELECT 1
        FROM shifts s
        WHERE s.caregiver_id = NEW.caregiver_id
          AND s.status != 'VOID'
          AND s.check_in_ts < COALESCE(NEW.check_out_ts, '9999-12-31T00:00:00Z')
          AND COALESCE(s.check_out_ts, '9999-12-31T00:00:00Z') > NEW.check_in_ts
      )
      THEN RAISE(ABORT, 'Caregiver overlap with another shift')
    END;
END;
"""

SQL_BEFORE_UPDATE = """
CREATE TRIGGER IF NOT EXISTS trg_shifts_no_overlap_upd
BEFORE UPDATE ON shifts
BEGIN
    -- end must be > start
    SELECT CASE
      WHEN NEW.check_out_ts IS NOT NULL AND NEW.check_out_ts <= NEW.check_in_ts
      THEN RAISE(ABORT, 'Shift end must be after start')
    END;

    -- caregiver cannot overlap own OPEN/CLOSED shifts (except VOID)
    SELECT CASE
      WHEN EXISTS (
        SELECT 1
        FROM shifts s
        WHERE s.caregiver_id = NEW.caregiver_id
          AND s.shift_id != NEW.shift_id
          AND s.status != 'VOID'
          AND s.check_in_ts < COALESCE(NEW.check_out_ts, '9999-12-31T00:00:00Z')
          AND COALESCE(s.check_out_ts, '9999-12-31T00:00:00Z') > NEW.check_in_ts
      )
      THEN RAISE(ABORT, 'Caregiver overlap with another shift')
    END;
END;
"""

def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    try:
        cur.execute(SQL_BEFORE_INSERT)
        cur.execute(SQL_BEFORE_UPDATE)
        conn.commit()
        print("Guardrail triggers created (no overlap, end>start).")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()
