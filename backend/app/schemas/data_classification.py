from pydantic import BaseModel
from datetime import datetime


class DataClassificationOut(BaseModel):
    id: str
    name: str
    description: str | None
    is_default: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DataClassificationCreate(BaseModel):
    name: str
    description: str | None = None
    is_default: bool = False


class DataClassificationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_default: bool | None = None
