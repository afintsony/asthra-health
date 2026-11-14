import time
from collections import defaultdict, deque
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.core.security import decode_token
from app.database.session import get_db
from app.models.entities import RevokedToken, SystemLog, User

bearer = HTTPBearer(auto_error=False)
STAFF = ("MEDICAL_OFFICER", "MISSION_CONTROL", "ADMIN")


def current_user(creds: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not creds:
        raise HTTPException(401, "Not authenticated")
    try:
        data = decode_token(creds.credentials, "access")
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")
    if db.get(RevokedToken, data["jti"]):
        raise HTTPException(401, "Token revoked")
    user = db.get(User, data["sub"])
    if not user or not user.is_active:
        raise HTTPException(401, "Inactive or unknown user")
    return user


def require_roles(*roles):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "Insufficient role")
        return user
    return dep


def can_access_astronaut(user: User, astronaut_id: str, *, private=False):
    """ASTRONAUT: own record only. `private` data (wellness) excludes MISSION_CONTROL."""
    if user.role == "ASTRONAUT":
        ok = user.astronaut_id == astronaut_id
    elif user.role == "MISSION_CONTROL":
        ok = not private
    else:
        ok = True
    if not ok:
        raise HTTPException(403, "Access to this astronaut's data is not permitted")


def audit(db: Session, user_id, action, detail=None):
    db.add(SystemLog(user_id=user_id, action=action, detail=detail))
    db.commit()


_hits = defaultdict(deque)


def rate_limit(limit=10, window=60):
    """Simple in-memory limiter (per client IP + path). Use a shared store for multi-instance deployments."""
    def dep(request: Request):
        key = (request.client.host if request.client else "?", request.url.path)
        now = time.time()
        q = _hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(429, "Too many requests")
        q.append(now)
    return dep
