from datetime import datetime, timezone
import jwt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import audit, current_user, rate_limit, require_roles
from app.core.security import (create_access_token, create_refresh_token, decode_token, hash_password,
                               verify_password)
from app.database.session import get_db
from app.models.entities import RevokedToken, User
from app.schemas.schemas import LoginIn, RefreshIn, RegisterIn

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _tokens(user: User):
    refresh, _ = create_refresh_token(user.id, user.role)
    return {"access_token": create_access_token(user.id, user.role), "refresh_token": refresh,
            "token_type": "bearer", "role": user.role, "astronaut_id": user.astronaut_id}


@router.post("/login", dependencies=[Depends(rate_limit(10, 60))])
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.username == body.username)).scalar_one_or_none()
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        audit(db, None, "login_failed", body.username[:64])
        raise HTTPException(401, "Invalid credentials")  # same message for unknown user / bad password
    audit(db, user.id, "login")
    return _tokens(user)


@router.post("/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db), admin: User = Depends(require_roles("ADMIN"))):
    if db.execute(select(User).where(User.username == body.username)).scalar_one_or_none():
        raise HTTPException(409, "Username already exists")
    u = User(username=body.username, password_hash=hash_password(body.password), role=body.role,
             astronaut_id=body.astronaut_id)
    db.add(u); db.commit()
    audit(db, admin.id, "user_created", f"{u.username}:{u.role}")
    return {"id": u.id, "username": u.username, "role": u.role}


@router.post("/refresh", dependencies=[Depends(rate_limit(20, 60))])
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    try:
        data = decode_token(body.refresh_token, "refresh")
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid refresh token")
    if db.get(RevokedToken, data["jti"]):
        raise HTTPException(401, "Refresh token revoked")
    user = db.get(User, data["sub"])
    if not user or not user.is_active:
        raise HTTPException(401, "Inactive user")
    db.add(RevokedToken(jti=data["jti"])); db.commit()  # rotation: old refresh token is single-use
    return _tokens(user)


@router.post("/logout")
def logout(body: RefreshIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        data = decode_token(body.refresh_token, "refresh")
        if not db.get(RevokedToken, data["jti"]):
            db.add(RevokedToken(jti=data["jti"])); db.commit()
    except jwt.PyJWTError:
        pass
    audit(db, user.id, "logout")
    return {"detail": "logged out"}
