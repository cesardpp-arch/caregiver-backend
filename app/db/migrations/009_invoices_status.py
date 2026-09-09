import sqlite3
from app.core.config import settings

DB = settings.DATABASE_PATH

def col_exists(cur, table, col):
    cur.execute(f"PRAGMA table_info({table});")
    return any(r[1] == col for r in cur.fetchall())

def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    try:
        if not col_exists(cur, "invoices", "status"):
            cur.execute("ALTER TABLE invoices ADD COLUMN status TEXT;")
            print("Added invoices.status")
        conn.commit()
        # Default existing to DRAFT if null
        cur.execute("UPDATE invoices SET status = COALESCE(status, 'DRAFT');")
        conn.commit()
        print("Initialized invoices.status to DRAFT")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()
