from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.uuid7 import uuid7_str
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


async def db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One session per request. Handlers commit explicitly; anything uncommitted is rolled back on close."""
    async with request.app.state.sessionmaker() as session:
        yield session


def correlation_id(request: Request) -> str:
    return request.headers.get("X-Correlation-ID") or uuid7_str()


def require_any_role(user: Principal, *roles: str) -> None:
    if not set(roles) & set(user.roles):
        raise HTTPException(403, f"requires one of the roles: {', '.join(roles)}")


CurrentUser = Annotated[Principal, Depends(current_user)]
Session = Annotated[AsyncSession, Depends(db_session)]
CorrelationId = Annotated[str, Depends(correlation_id)]
