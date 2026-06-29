import base64
from datetime import datetime

from pydantic import BaseModel, field_validator


class SnowflakeCredentialsConnect(BaseModel):
    project_name: str
    organization_name: str
    account_name: str
    user: str
    authenticator: str = "SNOWFLAKE_JWT"
    private_key_b64: str

    @field_validator("private_key_b64")
    @classmethod
    def must_be_valid_base64(cls, v: str) -> str:
        try:
            base64.b64decode(v, validate=True)
        except Exception:
            raise ValueError("private_key_b64 must be valid base64")
        return v


class SnowflakeCredentialsOut(BaseModel):
    id: str
    project_name: str
    organization_name: str
    account_name: str
    user: str
    authenticator: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
