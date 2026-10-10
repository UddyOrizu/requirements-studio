"""Development and test sign-in (RS_ENV=dev|test; never mounted in prod).

- DEV_USERS: the people in the samples, created by POST /dev/seed (and test fixtures) with password DEV_PASSWORD.
- POST /dev/token: a session token for any active user, without a password (UI tests, curl, Swagger).
- GET /dev/users: who can be picked on the sign-in page.
- GET /dev/emails: the newest queued/sent emails (read invitation and approval links in UI tests).
"""
from functools import cache
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import Session
from services.notifications.db import EmailOutbox

from .db import User
from .passwords import hash_password

DEV_PASSWORD = "requirements-studio-dev"
DEV_USERS: dict[str, dict] = {
    "user_admin": {"name": "Dev Admin", "email": "admin@example.com", "role": "admin", "title": "Administrator"},
    "user_sarah_lin": {"name": "Sarah Lin", "email": "sarah.lin@example.com", "role": "user",
                       "title": "Compliance Manager"},
    "user_daniel_okafor": {"name": "Daniel Okafor", "email": "daniel.okafor@example.com", "role": "admin",
                           "title": "Business Analyst"},
    "user_priya_shah": {"name": "Priya Shah", "email": "priya.shah@example.com", "role": "user",
                        "title": "Head of Compliance Operations"},
    "user_tom_reed": {"name": "Tom Reed", "email": "tom.reed@example.com", "role": "user", "title": "IT Architect"},
    "user_viewer": {"name": "Dev Viewer", "email": "viewer@example.com", "role": "user", "title": "Colleague"},
}


@cache
def _dev_hash() -> str:
    return hash_password(DEV_PASSWORD)


async def seed_dev_users(s: AsyncSession) -> None:
    """Create the dev users that do not exist yet (active, password DEV_PASSWORD)."""
    for user_id, u in DEV_USERS.items():
        if await s.get(User, user_id) is None:
            s.add(User(id=user_id, email=u["email"], name=u["name"], role=u["role"], status="active",
                       password_hash=_dev_hash(), session_version=0, failed_sign_ins=0, created_by="seed"))
    await s.flush()


def router() -> APIRouter:
    r = APIRouter(prefix="/dev", tags=["dev"])

    @r.get("/users")
    async def users(session: Session) -> list[dict]:
        rows = (await session.execute(select(User).where(User.status == "active").order_by(User.name))).scalars()
        return [{"user_id": u.id, "name": u.name, "email": u.email, "role": u.role,
                 "title": DEV_USERS.get(u.id, {}).get("title")} for u in rows]

    @r.post("/token")
    async def token(request: Request, session: Session, username: Annotated[str, Form()]) -> dict:
        """Form field `username`: a user id or email. Any password is ignored."""
        user = await session.get(User, username)
        if user is None:
            user = (await session.execute(select(User).where(User.email == username.lower()))).scalar_one_or_none()
        if user is None or user.status != "active":
            raise HTTPException(404, f"no active user {username}; POST /dev/seed creates the sample users")
        tokens = request.app.state.session_tokens
        return {"access_token": tokens.issue(user.id, user.session_version), "token_type": "Bearer",
                "expires_in": tokens.ttl}

    @r.get("/emails")
    async def emails(session: Session, to: str | None = None, limit: int = 20) -> list[dict]:
        q = select(EmailOutbox).order_by(EmailOutbox.created_at.desc(), EmailOutbox.id.desc()).limit(limit)
        if to:
            q = q.where(EmailOutbox.to_address == to.lower())
        return [{"id": str(e.id), "to": e.to_address, "subject": e.subject, "text": e.text_body,
                 "template": e.template, "status": e.status, "created_at": e.created_at}
                for e in (await session.execute(q)).scalars()]

    return r
