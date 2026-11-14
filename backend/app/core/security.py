from datetime import datetime, timedelta, timezone
import uuid
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from app.core.config import get_settings

_ph = PasswordHasher()
ROLES = ("ASTRONAUT", "MEDICAL_OFFICER", "MISSION_CONTROL", "ADMIN")


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    except (VerifyMismatchError, InvalidHashError):
        return False


def _token(sub: str, role: str, kind: str, delta: timedelta) -> tuple[str, str]:
    jti = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    payload = {"sub": sub, "role": role, "type": kind, "jti": jti, "iat": now, "exp": now + delta}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256"), jti


def create_access_token(sub, role):
    return _token(sub, role, "access", timedelta(minutes=get_settings().access_minutes))[0]


def create_refresh_token(sub, role):
    return _token(sub, role, "refresh", timedelta(days=get_settings().refresh_days))


def decode_token(token: str, expected_type: str) -> dict:
    data = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    if data.get("type") != expected_type:
        raise jwt.InvalidTokenError("wrong token type")
    return data
