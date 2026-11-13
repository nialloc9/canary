from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.api.deps import get_current_account_id
from app.core.database import get_db
from app.models.data_classification import DataClassification
from app.schemas.data_classification import (
    DataClassificationOut,
    DataClassificationCreate,
    DataClassificationUpdate,
)

router = APIRouter(prefix="/data-classifications", tags=["data-classifications"])


async def _get_or_404(db: AsyncSession, account_id: str, classification_id: str) -> DataClassification:
    result = await db.execute(
        select(DataClassification).where(
            DataClassification.account_id == account_id, DataClassification.id == classification_id
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Data classification not found")
    return record


async def _unset_other_defaults(db: AsyncSession, account_id: str, keep_id: str | None) -> None:
    result = await db.execute(
        select(DataClassification).where(
            DataClassification.account_id == account_id,
            DataClassification.is_default.is_(True),
            DataClassification.id != keep_id,
        )
    )
    for other in result.scalars().all():
        other.is_default = False


@router.get("", response_model=list[DataClassificationOut])
async def list_data_classifications(
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    result = await db.execute(
        select(DataClassification)
        .where(DataClassification.account_id == account_id)
        .order_by(DataClassification.sort_order)
    )
    return result.scalars().all()


@router.post("", response_model=DataClassificationOut, status_code=201)
async def create_data_classification(
    payload: DataClassificationCreate,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")

    existing = await db.execute(
        select(DataClassification).where(
            DataClassification.account_id == account_id, DataClassification.name == name
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"A classification named '{name}' already exists")

    next_sort_order = (
        await db.execute(
            select(func.coalesce(func.max(DataClassification.sort_order), -1)).where(
                DataClassification.account_id == account_id
            )
        )
    ).scalar_one() + 1

    record = DataClassification(
        account_id=account_id,
        name=name,
        description=payload.description,
        is_default=payload.is_default,
        sort_order=next_sort_order,
    )
    db.add(record)
    await db.flush()
    if payload.is_default:
        await _unset_other_defaults(db, account_id, record.id)
    return record


@router.put("/{classification_id}", response_model=DataClassificationOut)
async def update_data_classification(
    classification_id: str,
    payload: DataClassificationUpdate,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    record = await _get_or_404(db, account_id, classification_id)

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="name cannot be empty")
        if name != record.name:
            existing = await db.execute(
                select(DataClassification).where(
                    DataClassification.account_id == account_id, DataClassification.name == name
                )
            )
            if existing.scalar_one_or_none():
                raise HTTPException(status_code=409, detail=f"A classification named '{name}' already exists")
        record.name = name
    if payload.description is not None:
        record.description = payload.description
    if payload.is_default is not None:
        record.is_default = payload.is_default

    await db.flush()
    if record.is_default:
        await _unset_other_defaults(db, account_id, record.id)
    return record


@router.delete("/{classification_id}", status_code=204)
async def delete_data_classification(
    classification_id: str,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    record = await _get_or_404(db, account_id, classification_id)
    await db.delete(record)
