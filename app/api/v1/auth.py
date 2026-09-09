import time
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_caregiver
from app.core.config import settings
from app.core.security import create_access_token, verify_password, hash_password
from app.db.session import get_db
from app.models.tables import User, Client
from app.schemas.auth import ChangePasswordRequest, LoginRequest, TokenResponse

router = APIRouter()
_login_attempts: dict[str, list[float]] = {}
_login_attempts_lock = Lock()


def _login_attempt_key(email: str, client_ip: str) -> str:
    return f"{(email or '').strip().lower()}|{client_ip or 'unknown'}"


def _is_rate_limited(key: str) -> bool:
    now = time.time()
    window = max(60, int(settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS or 900))
    max_attempts = max(3, int(settings.LOGIN_RATE_LIMIT_MAX_ATTEMPTS or 10))

    with _login_attempts_lock:
        attempts = [ts for ts in _login_attempts.get(key, []) if now - ts <= window]
        _login_attempts[key] = attempts
        return len(attempts) >= max_attempts


def _register_failed_attempt(key: str) -> None:
    now = time.time()
    window = max(60, int(settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS or 900))

    with _login_attempts_lock:
        attempts = [ts for ts in _login_attempts.get(key, []) if now - ts <= window]
        attempts.append(now)
        _login_attempts[key] = attempts


def _clear_failed_attempts(key: str) -> None:
    with _login_attempts_lock:
        _login_attempts.pop(key, None)


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    key = _login_attempt_key(payload.email, client_ip)

    if _is_rate_limited(key):
        raise HTTPException(status_code=429, detail="Too many login attempts. Please try again later.")

    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        _register_failed_attempt(key)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user.status != "ACTIVE":
        _register_failed_attempt(key)
        raise HTTPException(status_code=403, detail="User inactive")

    _clear_failed_attempts(key)
    token = create_access_token(subject=user.email)
    return TokenResponse(access_token=token)


@router.get("/auth/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    client_name = None
    if getattr(user, "client_id", None):
        c = db.query(Client).filter(Client.client_id == user.client_id).first()
        client_name = c.name if c else None
    return {
        "user_id": user.user_id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "status": user.status,
        "must_change_password": bool(user.must_change_password),
        "client_id": getattr(user, "client_id", None),
        "client_name": client_name,
    }


@router.get("/auth/me/caregiver")
def me_caregiver(deps=Depends(require_caregiver)):
    user, cg = deps
    return {
        "user_id": user.user_id,
        "email": user.email,
        "role": user.role,
        "caregiver_id": cg.caregiver_id,
        "name": cg.name,
        "active": bool(cg.active),
        "must_change_password": bool(user.must_change_password),
    }


@router.post("/auth/change-password")
def change_password(payload: ChangePasswordRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    new_password = (payload.new_password or "").strip()
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")

    user.password_hash = hash_password(new_password)
    user.must_change_password = 0
    db.commit()

    return {"ok": True, "message": "Password updated"}
