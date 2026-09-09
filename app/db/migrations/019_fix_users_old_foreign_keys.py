import sqlite3

DB_PATH = r"C:\Shana\caregiver-system\data\caregiver.db"

SQL_CREATE_CAREGIVERS = """
CREATE TABLE caregivers (
  caregiver_id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id      INTEGER NOT NULL UNIQUE,
  name         TEXT NOT NULL,
  phone        TEXT,
  address      TEXT,
  active       INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
  FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
"""

SQL_CREATE_SHIFTS = """
CREATE TABLE shifts (
  shift_id      INTEGER PRIMARY KEY AUTOINCREMENT,
  client_id     INTEGER NOT NULL,
  caregiver_id  INTEGER NOT NULL,
  check_in_ts   TEXT NOT NULL,
  check_out_ts  TEXT,
  status        TEXT NOT NULL CHECK (status IN ('OPEN','CLOSED','VOID')),
  notes         TEXT,
  created_by    INTEGER,
  updated_by    INTEGER,
  created_at    TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
  start_date    TEXT,
  start_time    TEXT,
  end_date      TEXT,
  end_time      TEXT,
  FOREIGN KEY (client_id) REFERENCES clients(client_id),
  FOREIGN KEY (caregiver_id) REFERENCES caregivers(caregiver_id),
  FOREIGN KEY (created_by) REFERENCES users(user_id),
  FOREIGN KEY (updated_by) REFERENCES users(user_id)
);
"""

SQL_CREATE_AUDIT_LOGS = """
CREATE TABLE audit_logs (
  audit_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  entity     TEXT NOT NULL,
  entity_id  TEXT NOT NULL,
  action     TEXT NOT NULL,
  actor_id   INTEGER,
  before     TEXT,
  after      TEXT,
  at         TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (actor_id) REFERENCES users(user_id)
);
"""

SQL_TRG_INS = """
CREATE TRIGGER trg_shifts_no_overlap_ins
BEFORE INSERT ON shifts
BEGIN
    SELECT CASE
      WHEN NEW.check_out_ts IS NOT NULL AND NEW.check_out_ts <= NEW.check_in_ts
      THEN RAISE(ABORT, 'Shift end must be after start')
    END;

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

SQL_TRG_UPD = """
CREATE TRIGGER trg_shifts_no_overlap_upd
BEFORE UPDATE ON shifts
BEGIN
    SELECT CASE
      WHEN NEW.check_out_ts IS NOT NULL AND NEW.check_out_ts <= NEW.check_in_ts
      THEN RAISE(ABORT, 'Shift end must be after start')
    END;

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


def table_sql(cur, name: str) -> str:
    row = cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return (row[0] if row and row[0] else "")


def references_users_old(cur, table: str) -> bool:
    return "users_old" in table_sql(cur, table).lower()


def table_exists(cur, table: str) -> bool:
    row = cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return bool(row)


def rebuild_caregivers(cur):
    cur.execute("ALTER TABLE caregivers RENAME TO caregivers_fix_old;")
    cur.execute(SQL_CREATE_CAREGIVERS)
    cur.execute(
        """
        INSERT INTO caregivers (caregiver_id, user_id, name, phone, address, active)
        SELECT caregiver_id, user_id, name, phone, address, active
        FROM caregivers_fix_old;
        """
    )
    cur.execute("DROP TABLE caregivers_fix_old;")


def rebuild_shifts(cur):
    cur.execute("DROP TRIGGER IF EXISTS trg_shifts_no_overlap_ins;")
    cur.execute("DROP TRIGGER IF EXISTS trg_shifts_no_overlap_upd;")

    cur.execute("ALTER TABLE shifts RENAME TO shifts_fix_old;")
    cur.execute(SQL_CREATE_SHIFTS)
    cur.execute(
        """
        INSERT INTO shifts (
            shift_id, client_id, caregiver_id, check_in_ts, check_out_ts, status,
            notes, created_by, updated_by, created_at, updated_at,
            start_date, start_time, end_date, end_time
        )
        SELECT
            shift_id, client_id, caregiver_id, check_in_ts, check_out_ts, status,
            notes, created_by, updated_by, created_at, updated_at,
            start_date, start_time, end_date, end_time
        FROM shifts_fix_old;
        """
    )
    cur.execute("DROP TABLE shifts_fix_old;")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_shifts_client ON shifts(client_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_shifts_caregiver ON shifts(caregiver_id);")
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_open_shift_per_caregiver
        ON shifts(caregiver_id)
        WHERE status='OPEN';
        """
    )

    cur.execute(SQL_TRG_INS)
    cur.execute(SQL_TRG_UPD)


def rebuild_audit_logs(cur):
    cur.execute("ALTER TABLE audit_logs RENAME TO audit_logs_fix_old;")
    cur.execute(SQL_CREATE_AUDIT_LOGS)
    cur.execute(
        """
        INSERT INTO audit_logs (audit_id, entity, entity_id, action, actor_id, before, after, at)
        SELECT audit_id, entity, entity_id, action, actor_id, before, after, at
        FROM audit_logs_fix_old;
        """
    )
    cur.execute("DROP TABLE audit_logs_fix_old;")


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    needs_caregivers = table_exists(cur, "caregivers") and references_users_old(cur, "caregivers")
    needs_shifts = table_exists(cur, "shifts") and references_users_old(cur, "shifts")
    needs_audit = table_exists(cur, "audit_logs") and references_users_old(cur, "audit_logs")

    if not (needs_caregivers or needs_shifts or needs_audit):
        print("Migration 019 skipped: no users_old foreign keys found")
        conn.close()
        return

    cur.execute("PRAGMA foreign_keys = OFF;")
    conn.commit()

    try:
        cur.execute("BEGIN;")

        if needs_caregivers:
            rebuild_caregivers(cur)
        if needs_shifts:
            rebuild_shifts(cur)
        if needs_audit:
            rebuild_audit_logs(cur)

        cur.execute("COMMIT;")
        print("Migration 019 complete: fixed foreign keys from users_old to users")
    except Exception:
        cur.execute("ROLLBACK;")
        raise
    finally:
        cur.execute("PRAGMA foreign_keys = ON;")
        conn.commit()
        conn.close()


if __name__ == "__main__":
    main()
