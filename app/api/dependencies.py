from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session

from app.core.security import verify_token
from app.db.session import get_db
from app.models.tables import User, Caregiver

def get_current_user(
        authorization: str = Header(None),
        db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1]
    email = verify_token(token)
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(
        User.email == email,
        User.status == "ACTIVE"
    ).first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user


def require_caregiver(
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
) -> tuple[User, Caregiver]:
    if user.role != "CAREGIVER":
        raise HTTPException(status_code=403, detail="Caregiver role required")

    cg = db.query(Caregiver).filter(
        Caregiver.user_id == user.user_id,
        Caregiver.active == 1
    ).first()

    if not cg:
        raise HTTPException(status_code=403, detail="Caregiver profile not found or inactive")

    return user, cg


def require_admin(
        user: User = Depends(get_current_user)
) -> User:
    if user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


def require_admin_or_supervisor(
        user: User = Depends(get_current_user)
) -> User:
    if user.role not in {"ADMIN", "SUPERVISOR"}:
        raise HTTPException(status_code=403, detail="Admin or Supervisor role required")
    return user


def require_reports_viewer(
        user: User = Depends(get_current_user)
) -> User:
    if user.role not in {"ADMIN", "SUPERVISOR", "CUSTOMER"}:
        raise HTTPException(status_code=403, detail="Reports access role required")
    return user
