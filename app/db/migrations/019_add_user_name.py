"""Add optional name column to users table."""

import sqlite3

DB_PATH = r"C:\Shana\caregiver-system\data\caregiver.db"


def has_column(cur: sqlite3.Cursor, table: str, column: str) -> bool:
    cur.execute(f"PRAGMA table_info({table});")
    cols = [r[1] for r in cur.fetchall()]
    return column in cols


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    try:
        if has_column(cur, "users", "name"):
            print("Migration 019 skipped: users.name already exists")
            return

        cur.execute("ALTER TABLE users ADD COLUMN name TEXT;")
        conn.commit()
        print("Migration 019 complete: added users.name")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
