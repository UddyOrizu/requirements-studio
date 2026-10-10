"""Internal user management (docs/06 §Identity): accounts, invitations, password sign-in and resets, and mapping
Microsoft Entra ID sign-ins onto accounts an admin has added.

Roles: `user` and `admin`. Admins manage users; ownership of ideas and processes stays per record. Every change is
audited in the caller's transaction; emails are queued in that same transaction (services/notifications).
"""
import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.db import utcnow
from services.common.errors import InvalidInput
from services.common.settings import Settings
from services.ir_store.service import Conflict, NotFound
from services.notifications import queue_email

from .audit import write_audit
from .auth import InvalidToken, Principal
from .db import User, UserToken
from .passwords import hash_password, needs_rehash, policy_problem, verify_password
from .sessions import SessionClaims

ROLES = ("user", "admin")
STATUSES = ("invited", "active", "disabled")
INVITE_TTL = timedelta(days=7)
RESET_TTL = timedelta(hours=1)
LOCK_AFTER = 5
LOCK_FOR = timedelta(minutes=15)
SIGN_IN_FAILED = (f"Email or password is incorrect. After {LOCK_AFTER} failed attempts, sign-in is paused for "
                  f"{int(LOCK_FOR.total_seconds() // 60)} minutes.")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SignInFailed(Exception):
    """401. Always the same message, so it does not reveal whether an account exists."""


class NotRegistered(Exception):
    """403: an SSO sign-in by someone no admin has added (or who is disabled)."""


@dataclass(frozen=True)
class Link:
    url: str
    expires_at: datetime


def normalise_email(email: str) -> str:
    return email.strip().lower()


def principal(user: User) -> Principal:
    return Principal(user_id=user.id, name=user.name, email=user.email, roles=(user.role,))


def public(user: User) -> dict:
    """What admins see (never the hash)."""
    return {"user_id": user.id, "email": user.email, "name": user.name, "role": user.role, "status": user.status,
            "sso_linked": user.entra_oid is not None, "has_password": user.password_hash is not None,
            "locked": user.locked_until is not None and user.locked_until > utcnow(),
            "last_sign_in_at": user.last_sign_in_at, "created_at": user.created_at, "created_by": user.created_by}


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class UserService:
    def __init__(self, session: AsyncSession, *, settings: Settings, clock=utcnow):
        self.s, self.settings, self.clock = session, settings, clock

    # ------------------------------------------------------------------ reads
    async def get(self, user_id: str, *, lock: bool = False) -> User:
        user = await self.s.get(User, user_id, with_for_update=lock)
        if user is None:
            raise NotFound(f"user {user_id} not found")
        return user

    async def by_email(self, email: str) -> User | None:
        q = select(User).where(func.lower(User.email) == normalise_email(email))
        return (await self.s.execute(q)).scalar_one_or_none()

    async def search(self, *, q: str | None = None, status: str | None = None, role: str | None = None) -> list[User]:
        query = select(User).order_by(func.lower(User.name))
        if q:
            like = f"%{q.strip().lower()}%"
            query = query.where(or_(func.lower(User.name).like(like), func.lower(User.email).like(like)))
        if status:
            query = query.where(User.status == status)
        if role:
            query = query.where(User.role == role)
        return list((await self.s.execute(query)).scalars())

    async def directory(self) -> list[dict]:
        """Everyone who can be asked for something (people pickers): not disabled."""
        rows = await self.search()
        return [{"user_id": u.id, "name": u.name, "email": u.email, "role": u.role} for u in rows
                if u.status != "disabled"]

    async def display_name(self, user_id: str | None) -> str:
        if not user_id:
            return ""
        user = await self.s.get(User, user_id)
        return user.name if user else user_id

    # ------------------------------------------------------------------ admin
    async def create(self, *, email: str, name: str, role: str, actor: Principal | None,
                     send_invite: bool = True, user_id: str | None = None) -> User:
        email, name = normalise_email(email), name.strip()
        if not EMAIL.match(email):
            raise InvalidInput("/email", "enter a valid email address")
        if not name:
            raise InvalidInput("/name", "enter the person's name")
        if role not in ROLES:
            raise InvalidInput("/role", f"role must be one of {', '.join(ROLES)}")
        if await self.by_email(email) is not None:
            raise Conflict("/problems/user-exists", f"{email} already has an account")
        user = User(id=user_id or await self._free_id(name), email=email, name=name, role=role, status="invited",
                    session_version=0, failed_sign_ins=0, created_by=actor.user_id if actor else None)
        self.s.add(user)
        await self.s.flush()
        await self._audit(actor, "user.created", user, after={"email": email, "name": name, "role": role})
        if send_invite:
            await self.invite(user.id, actor=actor)
        return user

    async def update(self, user_id: str, *, actor: Principal, name: str | None = None, role: str | None = None,
                     status: str | None = None) -> User:
        user = await self.get(user_id, lock=True)
        before = {"name": user.name, "role": user.role, "status": user.status}
        if name is not None:
            if not name.strip():
                raise InvalidInput("/name", "enter the person's name")
            user.name = name.strip()
        if role is not None and role != user.role:
            if role not in ROLES:
                raise InvalidInput("/role", f"role must be one of {', '.join(ROLES)}")
            if user.role == "admin":
                await self._keep_an_admin(user, "demote")
            user.role = role
        if status is not None and status != user.status:
            if status not in ("active", "disabled"):
                raise InvalidInput("/status", "status can be set to active or disabled")
            if status == "disabled":
                if user.id == actor.user_id:
                    raise Conflict("/problems/cannot-disable-self", "you cannot disable your own account")
                if user.role == "admin":
                    await self._keep_an_admin(user, "disable")
                user.session_version += 1  # signs them out everywhere
                user.status = "disabled"
            else:  # re-enable: back to invited until they have a way to sign in
                user.status = "active" if user.password_hash or user.entra_oid else "invited"
        after = {"name": user.name, "role": user.role, "status": user.status}
        if after != before:
            action = "user.updated"
            if user.status == "disabled" and before["status"] != "disabled":
                action = "user.disabled"
            elif before["status"] == "disabled" and user.status != "disabled":
                action = "user.enabled"
            await self._audit(actor, action, user, before=before, after=after)
        await self.s.flush()
        return user

    async def _keep_an_admin(self, user: User, verb: str) -> None:
        others = (await self.s.execute(select(func.count()).select_from(User).where(
            User.role == "admin", User.status != "disabled", User.id != user.id))).scalar_one()
        if not others:
            raise Conflict("/problems/last-admin", f"cannot {verb} the last administrator; make someone else an "
                                                   "admin first")

    async def invite(self, user_id: str, *, actor: Principal | None) -> Link:
        """(Re)send the invitation: a set-password link, or with SSO only, a link to the sign-in page."""
        user = await self.get(user_id)
        if user.status == "disabled":
            raise Conflict("/problems/user-disabled", "enable the account before inviting")
        inviter = actor.name if actor and actor.name else "An administrator"
        sso = self.settings.sso_enabled
        if self.settings.password_sign_in and user.password_hash is None:
            link = await self._issue(user, "invite", INVITE_TTL, actor)
            context = {"link_is_password": True, "link": link.url}
        else:
            link = Link(f"{self._web}/signin", self.clock())
            context = {"link_is_password": False, "link": link.url}
        await queue_email(self.s, to_address=user.email, to_name=user.name, template="invite", related_id=user.id,
                          context={**context, "inviter_name": inviter, "role": user.role, "sso": sso,
                                   "expires_days": INVITE_TTL.days, "action_label": "Get started"})
        await self._audit(actor, "user.invited", user)
        return link

    async def admin_reset(self, user_id: str, *, actor: Principal) -> Link:
        user = await self.get(user_id)
        if not self.settings.password_sign_in:
            raise Conflict("/problems/passwords-off", "password sign-in is turned off (RS_PASSWORD_SIGN_IN=false)")
        if user.status == "disabled":
            raise Conflict("/problems/user-disabled", "enable the account before resetting its password")
        return await self._send_reset(user, actor=actor)

    # ------------------------------------------------------------------ self-service
    async def forgot_password(self, email: str) -> None:
        """Public. Sends a reset link when the account can use one; says nothing either way."""
        user = await self.by_email(email)
        if user is None or user.status == "disabled" or not self.settings.password_sign_in:
            return
        await self._send_reset(user, actor=None)

    async def _send_reset(self, user: User, *, actor: Principal | None) -> Link:
        link = await self._issue(user, "reset", RESET_TTL, actor)
        await queue_email(self.s, to_address=user.email, to_name=user.name, template="password_reset",
                          related_id=user.id,
                          context={"link": link.url, "email": user.email, "by_admin": actor is not None,
                                   "expires_minutes": int(RESET_TTL.total_seconds() // 60),
                                   "action_label": "Choose a new password"})
        await self._audit(actor, "user.password_reset_requested", user)
        return link

    async def token_info(self, token: str) -> tuple[UserToken, User]:
        row = (await self.s.execute(select(UserToken).where(UserToken.token_hash == _digest(token))
                                    .with_for_update())).scalar_one_or_none()
        if row is None or row.used_at is not None or row.expires_at <= self.clock():
            raise Conflict("/problems/link-expired", "this link has expired or was already used; ask for a new one")
        user = await self.get(row.user_id, lock=True)
        if user.status == "disabled":
            raise Conflict("/problems/link-expired", "this account is disabled")
        return row, user

    async def set_password(self, token: str, password: str) -> User:
        """Invitation or reset link → password set, account active, every other session signed out."""
        if not self.settings.password_sign_in:
            raise Conflict("/problems/passwords-off", "password sign-in is turned off")
        row, user = await self.token_info(token)
        if problem := policy_problem(password, email=user.email):
            raise InvalidInput("/password", problem)
        now = self.clock()
        row.used_at = now
        user.password_hash = hash_password(password)
        user.status, user.failed_sign_ins, user.locked_until = "active", 0, None
        user.session_version += 1
        await self._audit(Principal(user.id), "user.password_set", user, after={"via": row.purpose})
        await self.s.flush()
        return user

    async def change_password(self, user_id: str, *, current: str, new: str) -> User:
        user = await self.get(user_id, lock=True)
        if not verify_password(user.password_hash, current):
            raise InvalidInput("/current_password", "your current password is not right")
        if problem := policy_problem(new, email=user.email):
            raise InvalidInput("/new_password", problem)
        user.password_hash = hash_password(new)
        user.session_version += 1
        await self._audit(Principal(user.id), "user.password_changed", user)
        await self.s.flush()
        return user

    # ------------------------------------------------------------------ sign-in
    async def sign_in(self, email: str, password: str) -> User:
        """Password sign-in. Failures are counted (commit before reporting them); LOCK_AFTER in a row lock it."""
        if not self.settings.password_sign_in:
            raise SignInFailed("password sign-in is turned off; sign in with Microsoft")
        user = await self.by_email(email)
        now = self.clock()
        if user is None or user.status == "disabled" or user.password_hash is None:
            verify_password(None, password)  # same work as a real check
            raise SignInFailed(SIGN_IN_FAILED)
        if user.locked_until and user.locked_until > now:
            raise SignInFailed(SIGN_IN_FAILED)
        if not verify_password(user.password_hash, password):
            user.failed_sign_ins += 1
            if user.failed_sign_ins >= LOCK_AFTER:
                user.failed_sign_ins, user.locked_until = 0, now + LOCK_FOR
                await self._audit(None, "user.locked", user, after={"until": user.locked_until.isoformat()})
            await self.s.flush()
            raise SignInFailed(SIGN_IN_FAILED)
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        user.failed_sign_ins, user.locked_until, user.last_sign_in_at = 0, None, now
        await self.s.flush()
        return user

    async def for_session(self, claims: SessionClaims) -> User:
        user = await self.s.get(User, claims.user_id)
        if user is None or user.status != "active" or user.session_version != claims.session_version:
            raise InvalidToken("your session has ended; sign in again")
        return user

    async def for_entra(self, p: Principal) -> tuple[User, bool]:
        """An Entra ID sign-in → the account an admin added: by object id once linked, else by email (then linked).
        Returns (user, changed); the caller commits when changed."""
        oid = p.user_id
        user = (await self.s.execute(select(User).where(User.entra_oid == oid))).scalar_one_or_none()
        changed = False
        if user is None:
            user = await self.by_email(p.email) if p.email else None
            if user is None or user.entra_oid is not None:
                raise NotRegistered(f"{p.email or 'this account'} is not registered in Requirements Studio; ask an "
                                    "administrator to add you")
            user.entra_oid = oid
            await self._audit(Principal(user.id), "user.sso_linked", user, after={"entra_oid": oid})
            changed = True
        if user.status == "disabled":
            raise NotRegistered("your Requirements Studio account is disabled")
        now = self.clock()
        if user.status == "invited":
            user.status, changed = "active", True
        if user.last_sign_in_at is None or now - user.last_sign_in_at > timedelta(hours=1):
            user.last_sign_in_at, changed = now, True
        await self.s.flush()
        return user, changed

    # ------------------------------------------------------------------ helpers
    @property
    def _web(self) -> str:
        return self.settings.web_base_url.rstrip("/")

    async def _issue(self, user: User, purpose: str, ttl: timedelta, actor: Principal | None) -> Link:
        now = self.clock()
        earlier = await self.s.execute(select(UserToken).where(UserToken.user_id == user.id,
                                                               UserToken.purpose == purpose,
                                                               UserToken.used_at.is_(None)))
        for row in earlier.scalars():
            row.used_at = now  # void: only the newest link works
        token = secrets.token_urlsafe(32)
        expires = now + ttl
        self.s.add(UserToken(user_id=user.id, purpose=purpose, token_hash=_digest(token), expires_at=expires,
                             created_by=actor.user_id if actor else None))
        await self.s.flush()
        return Link(f"{self._web}/set-password?token={token}", expires)

    async def _free_id(self, name: str) -> str:
        base = "user_" + (re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:50] or "person")
        candidate, n = base, 2
        while await self.s.get(User, candidate) is not None:
            candidate, n = f"{base}_{n}", n + 1
        return candidate

    async def _audit(self, actor: Principal | None, action: str, user: User, *, before=None, after=None) -> None:
        await write_audit(self.s, actor_kind="user" if actor else "system", actor_id=actor.user_id if actor else
                          "system", action=action, target=user.id, before=before, after=after)

