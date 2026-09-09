import sqlite3
from zoneinfo import ZoneInfo
from datetime import datetime
from app.core.config import settings

DB_PATH = r"C:\shana\caregiver-system\data\caregiver.db"

def utc_iso_to_local_parts(iso_str: str, tzname: str):
    dt_utc = datetime.fromisoformat(iso_str)
    if dt_utc.tzinfo is None:
        # assume UTC if missing tz
        dt_utc = dt_utc.replace(tzinfo=ZoneInfo("UTC"))
    dt_local = dt_utc.astimezone(ZoneInfo(tzname))
    return dt_local.strftime("%Y-%m-%d"), dt_local.strftime("%H:%M")

def ensure_columns(cur):
    cur.execute("PRAGMA table_info(shifts)")
    cols = {row[1] for row in cur.fetchall()}
    for col in ("start_date", "start_time", "end_date", "end_time"):
        if col not in cols:
            cur.execute(f"ALTER TABLE shifts ADD COLUMN {col} TEXT")

def backfill(conn):
    cur = conn.cursor()
    tz = settings.TIMEZONE

    # backfill start_date/start_time from check_in_ts
    cur.execute("SELECT shift_id, check_in_ts FROM shifts WHERE check_in_ts IS NOT NULL")
    for shift_id, cin in cur.fetchall():
        sd, st = utc_iso_to_local_parts(cin, tz)
        cur.execute(
            "UPDATE shifts SET start_date=?, start_time=? WHERE shift_id=?",
            (sd, st, shift_id)
        )

    # backfill end_date/end_time from check_out_ts
    cur.execute("SELECT shift_id, check_out_ts FROM shifts WHERE check_out_ts IS NOT NULL")
    for shift_id, cout in cur.fetchall():
        ed, et = utc_iso_to_local_parts(cout, tz)
        cur.execute(
            "UPDATE shifts SET end_date=?, end_time=? WHERE shift_id=?",
            (ed, et, shift_id)
        )

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()
    ensure_columns(cur)
    backfill(conn)
    conn.commit()
    conn.close()
    print("Migration complete: added start_date/start_time/end_date/end_time and backfilled.")

if __name__ == "__main__":
    main()
