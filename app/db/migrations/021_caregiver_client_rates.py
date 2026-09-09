import sqlite3

DB_PATH = r"C:\Shana\caregiver-system\data\caregiver.db"


def table_exists(cur, table: str) -> bool:
    row = cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return bool(row)


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    try:
        if table_exists(cur, "caregiver_client_rates"):
            print("Migration 021 skipped: caregiver_client_rates already exists")
            return

        cur.execute("PRAGMA foreign_keys = OFF;")
        conn.commit()

        cur.execute(
            """
            CREATE TABLE caregiver_client_rates (
                rate_id INTEGER PRIMARY KEY AUTOINCREMENT,
                caregiver_id INTEGER NOT NULL,
                client_id INTEGER NOT NULL,
                pay_day REAL NOT NULL DEFAULT 0,
                pay_night REAL NOT NULL DEFAULT 0,
                FOREIGN KEY (caregiver_id) REFERENCES caregivers(caregiver_id) ON DELETE CASCADE,
                FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE,
                UNIQUE (caregiver_id, client_id)
            );
            """
        )

        cur.execute(
            """
            INSERT INTO caregiver_client_rates (caregiver_id, client_id, pay_day, pay_night)
            SELECT cg.caregiver_id, cl.client_id,
                   COALESCE(cl.pay_day, 0),
                   COALESCE(cl.pay_night, 0)
            FROM caregivers cg
            CROSS JOIN clients cl;
            """
        )

        cur.execute("CREATE INDEX IF NOT EXISTS idx_cg_rates_caregiver ON caregiver_client_rates(caregiver_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cg_rates_client ON caregiver_client_rates(client_id);")

        conn.commit()
        print("Migration 021 complete: caregiver_client_rates created and seeded")
    finally:
        cur.execute("PRAGMA foreign_keys = ON;")
        conn.commit()
        conn.close()


if __name__ == "__main__":
    main()
