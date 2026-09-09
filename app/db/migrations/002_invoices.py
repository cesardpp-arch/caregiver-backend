import sqlite3

DB_PATH = r"C:\shana\caregiver-system\data\caregiver.db"

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
                CREATE TABLE IF NOT EXISTS invoices (
                                                        invoice_id INTEGER PRIMARY KEY,
                                                        client_id INTEGER NOT NULL,
                                                        from_utc TEXT NOT NULL,
                                                        to_utc   TEXT NOT NULL,
                                                        created_at TEXT NOT NULL,
                                                        total_amount REAL NOT NULL DEFAULT 0.0,
                                                        notes TEXT,
                                                        FOREIGN KEY(client_id) REFERENCES clients(client_id)
                    );
                """)

    cur.execute("""
                CREATE TABLE IF NOT EXISTS invoice_items (
                                                             item_id INTEGER PRIMARY KEY,
                                                             invoice_id INTEGER NOT NULL,
                                                             shift_id INTEGER NOT NULL,
                                                             desc TEXT NOT NULL,
                                                             hours_day REAL NOT NULL DEFAULT 0.0,
                                                             hours_night REAL NOT NULL DEFAULT 0.0,
                                                             rate_day REAL NOT NULL DEFAULT 0.0,
                                                             rate_night REAL NOT NULL DEFAULT 0.0,
                                                             amount REAL NOT NULL DEFAULT 0.0,
                                                             FOREIGN KEY(invoice_id) REFERENCES invoices(invoice_id) ON DELETE CASCADE,
                    FOREIGN KEY(shift_id) REFERENCES shifts(shift_id)
                    );
                """)

    # Unique index: each shift can appear on at most one invoice item
    cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS ux_invoice_items_shift
                    ON invoice_items(shift_id);
                """)

    conn.commit()
    conn.close()
    print("Migration 002 OK: invoices + invoice_items + unique index.")

if __name__ == "__main__":
    main()
