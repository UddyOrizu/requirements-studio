from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Index, Text, func
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
