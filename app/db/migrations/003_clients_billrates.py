import sqlite3

DB_PATH = r"C:\Shana\caregiver-system\data\caregiver.db"

def column_exists(cur, table, col):
    cur.execute(f"PRAGMA table_info({table});")
    return any(row[1] == col for row in cur.fetchall())

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    if not column_exists(cur, "clients", "bill_day"):
        cur.execute("ALTER TABLE clients ADD COLUMN bill_day REAL;")
        print("Added clients.bill_day")

    if not column_exists(cur, "clients", "bill_night"):
        cur.execute("ALTER TABLE clients ADD COLUMN bill_night REAL;")
        print("Added clients.bill_night")

    conn.commit()
    conn.close()
    print("Migration 003 complete.")

if __name__ == "__main__":
    main()
