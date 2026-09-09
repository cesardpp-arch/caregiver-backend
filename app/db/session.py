from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
print("### DB URI in use:", settings.SQLALCHEMY_DATABASE_URI)

SQLALCHEMY_DATABASE_URI = settings.SQLALCHEMY_DATABASE_URI
# example: "sqlite:///C:/Shana/caregiver-system/data/caregiver.db"

engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    connect_args={
        "check_same_thread": False,  # required for SQLite + FastAPI
        "timeout": 15,               # avoid "database is locked"
    },
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    try:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute("PRAGMA foreign_keys=ON;")
        cur.close()
    except Exception:
        pass
