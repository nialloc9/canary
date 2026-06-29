from datetime import datetime, timezone, timedelta

import jwt
from passlib.context import CryptContext

from app.core.config import get_settings

ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthError(Exception):
    pass


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def create_access_token(user_id: str, account_id: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {"sub": user_id, "account_id": account_id, "type": ACCESS_TOKEN_TYPE, "exp": expire},
        settings.secret_key,
        algorithm=ALGORITHM,
    )


def create_refresh_token(user_id: str, account_id: str, jti: str) -> str:
    """Issue a non-expiring refresh JWT. Revocation is handled via the DB jti record."""
    settings = get_settings()
    return jwt.encode(
        {"sub": user_id, "account_id": account_id, "jti": jti, "type": REFRESH_TOKEN_TYPE},
        settings.secret_key,
        algorithm=ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise AuthError("Access token has expired")
    except jwt.InvalidTokenError as exc:
        raise AuthError(f"Invalid token: {exc}")
    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise AuthError("Token is not an access token")
    return payload


def decode_refresh_token(token: str) -> dict:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITHM],
            options={"verify_exp": False},
        )
    except jwt.InvalidTokenError as exc:
        raise AuthError(f"Invalid refresh token: {exc}")
    if payload.get("type") != REFRESH_TOKEN_TYPE:
        raise AuthError("Token is not a refresh token")
    return payload
