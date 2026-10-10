"""Sign-in (public, /auth/*), the signed-in person (/api/v1/me), the people directory and user management for
admins (/api/v1/admin/users). docs/03 §1 "Identity"."""
from typing import Annotated, Literal

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from apps.api.deps import CurrentUser, Session, require_admin
from apps.api.problems import problem

from .users import SignInFailed, UserService, public

auth_router = APIRouter(prefix="/auth", tags=["identity"])
router = APIRouter(tags=["identity"])


class LoginBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class ForgotBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class SetPasswordBody(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(min_length=1, max_length=1024)


class ChangePasswordBody(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=1, max_length=1024)


class NewUser(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    name: str = Field(min_length=1, max_length=200)
    role: Literal["user", "admin"] = "user"
    send_invite: bool = True


class UserChange(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    role: Literal["user", "admin"] | None = None
    status: Literal["active", "disabled"] | None = None


def _users(request: Request, session) -> UserService:
    return UserService(session, settings=request.app.state.settings, clock=request.app.state.clock)


def _session_response(request: Request, user) -> dict:
    tokens = request.app.state.session_tokens
    return {"access_token": tokens.issue(user.id, user.session_version), "token_type": "Bearer",
            "expires_in": tokens.ttl, "user": _me(user.id, user.name, user.email, user.role)}


def _me(user_id: str, name: str, email: str, role: str) -> dict:
    return {"user_id": user_id, "name": name, "email": email, "role": role, "roles": [role]}


# ---------------------------------------------------------------------------------------------------- public
@auth_router.get("/config")
def auth_config(request: Request) -> dict:
    """How the web app signs people in (public; no secrets)."""
    s = request.app.state.settings
    sso = None
    if s.sso_enabled:
        sso = {"provider": "entra", "client_id": s.entra_spa_client_id,
               "authority": f"{s.entra_authority.rstrip('/')}/{s.entra_tenant_id}", "scopes": [s.api_scope]}
    return {"password": s.password_sign_in, "sso": sso, "dev_sign_in": s.dev_sign_in}


async def _sign_in(request: Request, session, email: str, password: str):
    users = _users(request, session)
    try:
        user = await users.sign_in(email, password)
    except SignInFailed as e:
        await session.commit()  # keep the failure count
        return problem(401, "/problems/sign-in-failed", str(e))
    await session.commit()
    return _session_response(request, user)


@auth_router.post("/login")
async def login(body: LoginBody, request: Request, session: Session):
    return await _sign_in(request, session, body.email, body.password)


@auth_router.post("/token", include_in_schema=True)
async def token(request: Request, session: Session, username: Annotated[str, Form()],
                password: Annotated[str, Form()]):
    """OAuth2 password form (username = email), for curl and Swagger."""
    result = await _sign_in(request, session, username, password)
    if isinstance(result, JSONResponse):
        return result
    return {k: result[k] for k in ("access_token", "token_type", "expires_in")}


@auth_router.post("/password/forgot", status_code=202)
async def forgot(body: ForgotBody, request: Request, session: Session) -> dict:
    await _users(request, session).forgot_password(body.email)
    await session.commit()
    return {"status": "If that email has an account, a reset link is on its way."}


@auth_router.get("/password/link")
async def link_info(token: str, request: Request, session: Session) -> dict:
    """What the set-password page shows: invitation or reset, for whom."""
    row, user = await _users(request, session).token_info(token)
    return {"purpose": row.purpose, "email": user.email, "name": user.name, "expires_at": row.expires_at}


@auth_router.post("/password/set")
async def set_password(body: SetPasswordBody, request: Request, session: Session) -> dict:
    user = await _users(request, session).set_password(body.token, body.password)
    await session.commit()
    return _session_response(request, user)


# ---------------------------------------------------------------------------------------------------- signed in
@router.get("/me")
def me(user: CurrentUser) -> dict:
    if user.service:
        return {"user_id": user.user_id, "name": user.name, "email": user.email, "role": None,
                "roles": list(user.roles)}
    return _me(user.user_id, user.name, user.email, user.roles[0])


@router.post("/me/password")
async def change_password(body: ChangePasswordBody, request: Request, user: CurrentUser, session: Session) -> dict:
    changed = await _users(request, session).change_password(user.user_id, current=body.current_password,
                                                             new=body.new_password)
    await session.commit()
    return _session_response(request, changed)  # other sessions are signed out; this one continues


@router.get("/users")
async def directory(request: Request, user: CurrentUser, session: Session) -> list[dict]:
    """People who can be asked to approve or answer something."""
    return await _users(request, session).directory()


# ---------------------------------------------------------------------------------------------------- admin
@router.get("/admin/users")
async def list_users(request: Request, user: CurrentUser, session: Session, q: str | None = None,
                     status: Literal["invited", "active", "disabled"] | None = None,
                     role: Literal["user", "admin"] | None = None) -> list[dict]:
    require_admin(user)
    return [public(u) for u in await _users(request, session).search(q=q, status=status, role=role)]


@router.post("/admin/users", status_code=201)
async def create_user(body: NewUser, request: Request, user: CurrentUser, session: Session) -> dict:
    require_admin(user)
    created = await _users(request, session).create(email=body.email, name=body.name, role=body.role,
                                                     actor=user, send_invite=body.send_invite)
    await session.commit()
    return public(created)


@router.get("/admin/users/{user_id}")
async def get_user(user_id: str, request: Request, user: CurrentUser, session: Session) -> dict:
    require_admin(user)
    return public(await _users(request, session).get(user_id))


@router.patch("/admin/users/{user_id}")
async def update_user(user_id: str, body: UserChange, request: Request, user: CurrentUser, session: Session) -> dict:
    require_admin(user)
    if not body.model_fields_set:
        raise HTTPException(422, "nothing to change")
    changed = await _users(request, session).update(user_id, actor=user, **body.model_dump(exclude_unset=True))
    await session.commit()
    return public(changed)


@router.post("/admin/users/{user_id}/invite")
async def resend_invite(user_id: str, request: Request, user: CurrentUser, session: Session) -> dict:
    require_admin(user)
    link = await _users(request, session).invite(user_id, actor=user)
    await session.commit()
    return {"status": "sent", "expires_at": link.expires_at}


@router.post("/admin/users/{user_id}/password-reset")
async def reset_password(user_id: str, request: Request, user: CurrentUser, session: Session) -> dict:
    require_admin(user)
    link = await _users(request, session).admin_reset(user_id, actor=user)
    await session.commit()
    return {"status": "sent", "expires_at": link.expires_at}
