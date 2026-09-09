from app.db.session import SessionLocal
from app.models.tables import User
from app.core.security import verify_password

with SessionLocal() as db:
    for email in ['admin@test.com', 'adriana@gmail.com', 'care1@test.com']:
        u = db.query(User).filter(User.email == email).first()
        print(email, verify_password('Temp123!', u.password_hash) if u else None)
