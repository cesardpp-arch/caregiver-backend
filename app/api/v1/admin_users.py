from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin, get_current_user
from app.core.security import hash_password
from app.db.session import get_db
from app.models.tables import User, Client

router = APIRouter()

ALLOWED_MANAGED_ROLES = {"ADMIN", "SUPERVISOR", "CUSTOMER"}


class AdminUserCreate(BaseModel):
    name: str | None = None
    email: EmailStr
    password: str
    role: str
    active: int = 1
    client_id: int | None = None


class AdminUserUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    password: str | None = None
    role: str | None = None
    active: int | None = None
    client_id: int | None = None


def _validate_role(role: str) -> str:
    role_up = (role or "").strip().upper()
    if role_up not in ALLOWED_MANAGED_ROLES:
        raise HTTPException(status_code=400, detail="Role must be ADMIN, SUPERVISOR, or CUSTOMER")
    return role_up


def _serialize_user(u: User) -> dict:
    return {
        "user_id": u.user_id,
        "name": getattr(u, "name", None),
        "email": u.email,
        "role": u.role,
        "status": u.status,
        "active": 1 if u.status == "ACTIVE" else 0,
        "client_id": getattr(u, "client_id", None),
    }


@router.get("/admin/users", response_model=list[dict])
def list_admin_profiles(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = (
        db.query(User)
        .filter(User.role.in_(tuple(ALLOWED_MANAGED_ROLES)))
        .order_by(User.user_id.asc())
        .all()
    )
    return [_serialize_user(u) for u in rows]


@router.post("/admin/users", response_model=dict)
def create_admin_profile(
    payload: AdminUserCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    email = payload.email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already exists")

    role = _validate_role(payload.role)
    password = (payload.password or "").strip()
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    client_id = payload.client_id
    if role == "CUSTOMER":
        if not client_id:
            raise HTTPException(status_code=400, detail="Customer profile requires linked client")
        exists_client = db.query(Client.client_id).filter(Client.client_id == client_id).first()
        if not exists_client:
            raise HTTPException(status_code=400, detail="Linked client not found")
    else:
        client_id = None

    u = User(
        name=(payload.name or "").strip() or None,
        email=email,
        password_hash=hash_password(password),
        role=role,
        status="ACTIVE" if int(payload.active or 0) == 1 else "INACTIVE",
        must_change_password=0,
        client_id=client_id,
    )
    db.add(u)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        msg = str(getattr(exc, "orig", exc)).lower()
        if "check constraint failed" in msg and "role" in msg:
            raise HTTPException(
                status_code=400,
                detail="Database role constraint is outdated. Run migration 017_expand_user_roles.py and retry."
            )
        raise HTTPException(status_code=400, detail=str(getattr(exc, "orig", exc)))
    db.refresh(u)
    return _serialize_user(u)


@router.put("/admin/users/{user_id}", response_model=dict)
def update_admin_profile(
    user_id: int,
    payload: AdminUserUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    u = db.query(User).filter(User.user_id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    if u.role == "CAREGIVER":
        raise HTTPException(status_code=400, detail="Caregiver users are managed in Caregivers section")

    if payload.email is not None:
        email = payload.email.strip().lower()
        exists = db.query(User).filter(User.email == email, User.user_id != user_id).first()
        if exists:
            raise HTTPException(status_code=400, detail="Email already in use")
        u.email = email

    if payload.name is not None:
        u.name = payload.name.strip() or None

    new_role = u.role
    if payload.role is not None:
        new_role = _validate_role(payload.role)
        u.role = new_role

    if payload.password is not None and payload.password.strip():
        if len(payload.password.strip()) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
        u.password_hash = hash_password(payload.password.strip())
        u.must_change_password = 0

    if payload.active is not None:
        u.status = "ACTIVE" if int(payload.active or 0) == 1 else "INACTIVE"

    if new_role == "CUSTOMER":
        next_client_id = payload.client_id if payload.client_id is not None else u.client_id
        if not next_client_id:
            raise HTTPException(status_code=400, detail="Customer profile requires linked client")
        exists_client = db.query(Client.client_id).filter(Client.client_id == next_client_id).first()
        if not exists_client:
            raise HTTPException(status_code=400, detail="Linked client not found")
        u.client_id = next_client_id
    else:
        u.client_id = None

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        msg = str(getattr(exc, "orig", exc)).lower()
        if "check constraint failed" in msg and "role" in msg:
            raise HTTPException(
                status_code=400,
                detail="Database role constraint is outdated. Run migration 017_expand_user_roles.py and retry."
            )
        raise HTTPException(status_code=400, detail=str(getattr(exc, "orig", exc)))
    db.refresh(u)
    return _serialize_user(u)


@router.delete("/admin/users/{user_id}", status_code=204)
def delete_admin_profile(
    user_id: int,
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    u = db.query(User).filter(User.user_id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    if u.role == "CAREGIVER":
        raise HTTPException(status_code=400, detail="Caregiver users are managed in Caregivers section")
    if u.user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    db.delete(u)
    db.commit()
    return
