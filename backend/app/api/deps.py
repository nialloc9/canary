from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

import app.services.auth_service as auth_service
from app.services.auth_service import AuthError

_bearer = HTTPBearer()


async def get_current_account_id(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    try:
        payload = auth_service.decode_access_token(credentials.credentials)
        return payload["account_id"]
    except (AuthError, KeyError) as exc:
        raise HTTPException(status_code=401, detail=str(exc))
