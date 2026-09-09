import sqlite3

DB_PATH = r"C:\Shana\caregiver-system\data\caregiver.db"


def column_exists(cur, table: str, col: str) -> bool:
    cur.execute(f"PRAGMA table_info({table});")
    return any(row[1] == col for row in cur.fetchall())


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        if not column_exists(cur, "caregiver_client_rates", "is_custom"):
            cur.execute("ALTER TABLE caregiver_client_rates ADD COLUMN is_custom INTEGER NOT NULL DEFAULT 0;")
            conn.commit()
            print("Added caregiver_client_rates.is_custom")
        else:
            print("Migration 022 notice: caregiver_client_rates.is_custom already exists")

        # Existing auto-seeded rows remain non-custom by default.
        cur.execute("UPDATE caregiver_client_rates SET is_custom = 0 WHERE is_custom IS NULL;")
        conn.commit()
        print("Migration 022 complete: manual-only caregiver rate mode enabled")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
