import sqlite3

DB_PATH = r"C:\Shana\caregiver-system\data\caregiver.db"


def column_exists(cur, table, col):
    cur.execute(f"PRAGMA table_info({table});")
    return any(row[1] == col for row in cur.fetchall())


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    if not column_exists(cur, "clients", "invoice_anchor_dow"):
        cur.execute("ALTER TABLE clients ADD COLUMN invoice_anchor_dow INTEGER DEFAULT 6;")
        print("Added clients.invoice_anchor_dow (default=6 for Sunday)")

    if not column_exists(cur, "clients", "invoice_anchor_time"):
        cur.execute("ALTER TABLE clients ADD COLUMN invoice_anchor_time TEXT DEFAULT '23:00';")
        print("Added clients.invoice_anchor_time (default=23:00)")

    # Fill defaults for existing rows
    cur.execute("""
        UPDATE clients
        SET invoice_anchor_dow = COALESCE(NULLIF(invoice_anchor_dow, 0), 6),
            invoice_anchor_time = COALESCE(NULLIF(invoice_anchor_time, ''), '23:00')
        WHERE invoice_anchor_dow IS NULL OR invoice_anchor_time IS NULL
    """)

    conn.commit()
    conn.close()
    print("Migration 013 complete.")


if __name__ == "__main__":
    main()
