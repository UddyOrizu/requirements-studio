from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from services.common.db import Base, Timestamps
from services.common.uuid7 import uuid7


class AuditLog(Timestamps, Base):
    """Append-only (docs/06): a trigger rejects UPDATE/DELETE/TRUNCATE and the rs_app role has neither privilege.

    process_id has no foreign key on purpose: audit rows outlive the rows they describe.
    """

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_process_id_at", "process_id", "at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    process_id: Mapped[str | None] = mapped_column(Text)
    actor_kind: Mapped[str] = mapped_column(Text)  # user | agent | system
    actor_id: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)  # e.g. patch.applied, suggestion.accepted, export.created
    target: Mapped[str] = mapped_column(Text)  # what was acted on, e.g. patch id or /nodes/node_x
    before: Mapped[Any | None] = mapped_column(JSONB)
    after: Mapped[Any | None] = mapped_column(JSONB)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Timestamps, Base):
    """An internal account (docs/06 §Identity). Roles: user | admin. Ownership of ideas and processes is per record
    (owner_user_id), not a role. Users are disabled, never deleted: audit rows and ownership keep pointing at them.

    status: invited (no password yet; an SSO sign-in or setting a password activates) | active | disabled.
    session_version is part of every session token; bumping it signs the user out everywhere.
    """

    __tablename__ = "users"
    __table_args__ = (
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
        Index("uq_users_entra_oid", "entra_oid", unique=True, postgresql_where=text("entra_oid IS NOT NULL")),
        CheckConstraint("role IN ('user', 'admin')", name="role"),
        CheckConstraint("status IN ('invited', 'active', 'disabled')", name="status"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # user_<slug>
    email: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)  # user | admin
    status: Mapped[str] = mapped_column(Text)  # invited | active | disabled
    password_hash: Mapped[str | None] = mapped_column(Text)
    entra_oid: Mapped[str | None] = mapped_column(Text)
    session_version: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    failed_sign_ins: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sign_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(Text)


class UserToken(Timestamps, Base):
    """One-time links sent by email: invitations (set your password) and password resets. Only a SHA-256 of the
    token is stored; issuing a new one voids the user's earlier unused tokens of the same purpose."""

    __tablename__ = "user_tokens"
    __table_args__ = (Index("ix_user_tokens_user_id", "user_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    purpose: Mapped[str] = mapped_column(Text)  # invite | reset
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(Text)
