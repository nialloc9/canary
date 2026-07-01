from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_current_user_id
from app.core.database import get_db
from app.models.user import User
from app.schemas.auth import UserOut
import app.services.auth_service as auth_service

router = APIRouter(prefix="/users", tags=["users"])


class UpdateProfileRequest(BaseModel):
    username: str
    email: EmailStr


class UpdatePasswordRequest(BaseModel):
    current: str
    next: str


@router.get("/me", response_model=UserOut)
async def get_me(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/me", response_model=UserOut)
async def update_me(
    payload: UpdateProfileRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.username = payload.username
    user.email = payload.email
    await db.flush()
    return user


@router.put("/me/password", status_code=204)
async def update_password(
    payload: UpdatePasswordRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not auth_service.verify_password(payload.current, user.hashed_password):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    if len(payload.next) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")
    user.hashed_password = auth_service.hash_password(payload.next)
    await db.flush()
