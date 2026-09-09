import sqlite3

DB_PATH = r"C:\Shana\caregiver-system\data\caregiver.db"


def column_exists(cur, table, col):
    cur.execute(f"PRAGMA table_info({table});")
    return any(row[1] == col for row in cur.fetchall())


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    if not column_exists(cur, "users", "must_change_password"):
        cur.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0;")
        print("Added users.must_change_password")

    # Force all current caregivers to reset once; admins stay unchanged.
    cur.execute("UPDATE users SET must_change_password = 1 WHERE role = 'CAREGIVER';")

    conn.commit()
    conn.close()
    print("Migration 014 complete.")


if __name__ == "__main__":
    main()
