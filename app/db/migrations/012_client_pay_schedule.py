import sqlite3

DB_PATH = r"C:\Shana\caregiver-system\data\caregiver.db"


def column_exists(cur, table, col):
    cur.execute(f"PRAGMA table_info({table});")
    return any(row[1] == col for row in cur.fetchall())


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    if not column_exists(cur, "clients", "pay_day"):
        cur.execute("ALTER TABLE clients ADD COLUMN pay_day REAL;")
        print("Added clients.pay_day")

    if not column_exists(cur, "clients", "pay_night"):
        cur.execute("ALTER TABLE clients ADD COLUMN pay_night REAL;")
        print("Added clients.pay_night")

    if not column_exists(cur, "clients", "day_window_start"):
        cur.execute("ALTER TABLE clients ADD COLUMN day_window_start TEXT DEFAULT '07:00';")
        print("Added clients.day_window_start")

    if not column_exists(cur, "clients", "day_window_end"):
        cur.execute("ALTER TABLE clients ADD COLUMN day_window_end TEXT DEFAULT '23:00';")
        print("Added clients.day_window_end")

    # Fill defaults for older rows where schedule is still null/empty
    cur.execute("""
        UPDATE clients
        SET day_window_start = COALESCE(NULLIF(day_window_start, ''), '07:00'),
            day_window_end = COALESCE(NULLIF(day_window_end, ''), '23:00')
    """)

    conn.commit()
    conn.close()
    print("Migration 012 complete.")


if __name__ == "__main__":
    main()
