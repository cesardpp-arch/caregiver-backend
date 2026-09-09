import sqlite3

DB_PATH = r"C:\Shana\caregiver-system\data\caregiver.db"


def column_exists(cur, table: str, col: str) -> bool:
    cur.execute(f"PRAGMA table_info({table});")
    return any(row[1] == col for row in cur.fetchall())


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        if column_exists(cur, "users", "client_id"):
            print("Migration 018 skipped: users.client_id already exists")
            return

        cur.execute("ALTER TABLE users ADD COLUMN client_id INTEGER;")
        conn.commit()
        print("Migration 018 complete: added users.client_id for customer-client linkage")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
