from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.uuid7 import uuid7_str
from services.identity_audit.auth import InvalidToken, Principal

_bearer = HTTPBearer(auto_error=False)


async def db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One session per request. Handlers commit explicitly; anything uncommitted is rolled back on close."""
    async with request.app.state.sessionmaker() as session:
        yield session


async def current_user(
    request: Request, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> Principal:
    """The signed-in person, from a session token (password sign-in) or an Entra ID access token (SSO), always
    resolved to their internal account: the role comes from the users table, not from the token."""
    from services.identity_audit.users import NotRegistered, UserService, principal

    if creds is None:
        raise HTTPException(401, "missing bearer token", headers={"WWW-Authenticate": "Bearer"})
    token, state = creds.credentials, request.app.state
    users = UserService(session, settings=state.settings, clock=state.clock)
    try:
        if state.session_tokens.is_session_token(token):
            user = await users.for_session(state.session_tokens.verify(token))
        elif state.entra is not None:
            p = await run_in_threadpool(state.entra.verify, token)
            if p.service:
                return p  # app-only token (a service such as MOTHER): its app roles, no account
            user, changed = await users.for_entra(p)
            if changed:
                await session.commit()
        else:
            raise InvalidToken("not a Requirements Studio session token")
    except InvalidToken as e:
        raise HTTPException(401, f"invalid token: {e}", headers={"WWW-Authenticate": "Bearer"}) from e
    except NotRegistered as e:
        raise HTTPException(403, str(e)) from e
    return principal(user)


def correlation_id(request: Request) -> str:
    return request.headers.get("X-Correlation-ID") or uuid7_str()


def require_admin(user: Principal) -> None:
    if not user.is_admin:
        raise HTTPException(403, "only an administrator can do this")


CurrentUser = Annotated[Principal, Depends(current_user)]
Session = Annotated[AsyncSession, Depends(db_session)]
CorrelationId = Annotated[str, Depends(correlation_id)]
