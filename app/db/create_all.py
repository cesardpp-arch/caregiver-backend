from app.db.session import engine
from app.models.tables import Base

if __name__ == "__main__":
    print("Creating all tables in current DB...")
    Base.metadata.create_all(bind=engine)
    print("Done.")
