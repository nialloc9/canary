from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.user import Account, User, RefreshToken
from app.models.stack import Stack
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    RefreshRequest,
    LogoutRequest,
    UserOut,
)
import app.services.auth_service as auth_service
from app.services.auth_service import AuthError

router = APIRouter(prefix="/auth", tags=["auth"])
_bearer = HTTPBearer()


# ── Register ──────────────────────────────────────────────────────────────────

@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(User).where(
            (User.email == payload.email) | (User.username == payload.username)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email or username already in use")

    existing_domain = await db.execute(
        select(Account).where(Account.domain == payload.account_domain)
    )
    if existing_domain.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Domain already in use")

    account = Account(name=payload.account_name, domain=payload.account_domain)
    db.add(account)
    await db.flush()

    # Every account gets a "dev" stack (tracks develop) and a "prod" stack (tracks
    # main) — the release flow assumes both exist. "dev" is the default for new
    # conversations/experimentation.
    db.add(Stack(account_id=account.id, name="dev", branch="develop", sort_order=0, is_default=True))
    db.add(Stack(account_id=account.id, name="prod", branch="main", sort_order=1, is_default=False))
    await db.flush()

    user = User(
        account_id=account.id,
        email=payload.email,
        username=payload.username,
        hashed_password=auth_service.hash_password(payload.password),
    )
    db.add(user)
    await db.flush()
    return user


# ── Login ─────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(User.username == payload.username)
    )
    user = result.scalar_one_or_none()

    if not user or not auth_service.verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    token_record = RefreshToken(user_id=user.id)
    db.add(token_record)
    await db.flush()

    return TokenResponse(
        access_token=auth_service.create_access_token(user.id, user.account_id),
        refresh_token=auth_service.create_refresh_token(user.id, user.account_id, token_record.id),
    )


# ── Refresh ───────────────────────────────────────────────────────────────────

@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        claims = auth_service.decode_refresh_token(payload.refresh_token)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    jti = claims.get("jti")
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.id == jti)
    )
    token_record = result.scalar_one_or_none()

    if not token_record or token_record.revoked:
        raise HTTPException(status_code=401, detail="Refresh token has been revoked")

    return TokenResponse(
        access_token=auth_service.create_access_token(claims["sub"], claims["account_id"]),
        refresh_token=payload.refresh_token,
    )


# ── Logout ────────────────────────────────────────────────────────────────────

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: LogoutRequest,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
):
    try:
        auth_service.decode_access_token(credentials.credentials)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    try:
        claims = auth_service.decode_refresh_token(payload.refresh_token)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    jti = claims.get("jti")
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.id == jti)
    )
    token_record = result.scalar_one_or_none()

    if token_record and not token_record.revoked:
        token_record.revoked = True
