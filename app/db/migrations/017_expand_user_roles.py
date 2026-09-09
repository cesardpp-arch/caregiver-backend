import sqlite3

DB_PATH = r"C:\Shana\caregiver-system\data\caregiver.db"


def column_exists(cur, table: str, col: str) -> bool:
    cur.execute(f"PRAGMA table_info({table});")
    return any(row[1] == col for row in cur.fetchall())


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users';")
    row = cur.fetchone()
    if not row or not row[0]:
        conn.close()
        raise RuntimeError("users table not found")

    create_sql = row[0].upper()
    if "SUPERVISOR" in create_sql and "CUSTOMER" in create_sql:
        print("Migration 017 skipped: users.role already allows SUPERVISOR and CUSTOMER")
        conn.close()
        return

    if not column_exists(cur, "users", "must_change_password"):
        cur.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0;")
        conn.commit()

    cur.execute("PRAGMA foreign_keys = OFF;")
    conn.commit()

    try:
        cur.execute("BEGIN;")

        cur.execute("ALTER TABLE users RENAME TO users_old;")

        cur.execute(
            """
            CREATE TABLE users (
                user_id INTEGER PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('ADMIN','CAREGIVER','SUPERVISOR','CUSTOMER')),
                status TEXT NOT NULL CHECK (status IN ('ACTIVE','INACTIVE')),
                must_change_password INTEGER NOT NULL DEFAULT 0
            );
            """
        )

        cur.execute(
            """
            INSERT INTO users (user_id, email, password_hash, role, status, must_change_password)
            SELECT user_id, email, password_hash, role, status, COALESCE(must_change_password, 0)
            FROM users_old;
            """
        )

        cur.execute("DROP TABLE users_old;")

        cur.execute("COMMIT;")
        print("Migration 017 complete: expanded users.role to ADMIN/CAREGIVER/SUPERVISOR/CUSTOMER")
    except Exception:
        cur.execute("ROLLBACK;")
        raise
    finally:
        cur.execute("PRAGMA foreign_keys = ON;")
        conn.commit()
        conn.close()


if __name__ == "__main__":
    main()
