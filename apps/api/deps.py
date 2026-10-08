from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from services.identity_audit.auth import InvalidToken, Principal

_bearer = HTTPBearer(auto_error=False)


async def current_user(
    request: Request, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
) -> Principal:
    if creds is None:
        raise HTTPException(401, "missing bearer token", headers={"WWW-Authenticate": "Bearer"})
    try:
        return await run_in_threadpool(request.app.state.verifier.verify, creds.credentials)
    except InvalidToken as e:
        raise HTTPException(401, f"invalid token: {e}", headers={"WWW-Authenticate": "Bearer"}) from e


CurrentUser = Annotated[Principal, Depends(current_user)]
