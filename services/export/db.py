from typing import Any
from uuid import UUID

from sqlalchemy import CHAR, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

import services.ideas.db  # noqa: F401  (FK targets)
import services.ir_store.db  # noqa: F401
from services.common.db import Base, Timestamps
from services.common.uuid7 import uuid7


class ExportRow(Timestamps, Base):
    """One export: a file export (mode 'files') or a MOTHER package (P9). Never changed once written; a newer export
    of the same process sets `superseded_by` on the previous one."""

    __tablename__ = "exports"
    __table_args__ = (
        Index("uq_exports_process_id_ir_hash_mode", "process_id", "ir_hash", "mode", unique=True,
              postgresql_where=text("mode <> 'files'")),
        Index("uq_exports_process_id_package_hash", "process_id", "package_hash", unique=True,
              postgresql_where=text("mode = 'files'")),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    process_id: Mapped[str] = mapped_column(ForeignKey("processes.id"))
    ir_version: Mapped[int] = mapped_column(Integer)
    ir_hash: Mapped[str] = mapped_column(CHAR(64))
    package_hash: Mapped[str] = mapped_column(CHAR(64))
    mode: Mapped[str] = mapped_column(Text)  # files | full | partial
    uri: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    mother_import_id: Mapped[str | None] = mapped_column(Text)
    superseded_by: Mapped[UUID | None] = mapped_column(ForeignKey("exports.id"))
    idea_id: Mapped[str | None] = mapped_column(ForeignKey("ideas.id"))
    variant: Mapped[str | None] = mapped_column(Text)
    formats: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))
    files: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    draft: Mapped[bool] = mapped_column(server_default=text("false"))
    created_by: Mapped[str | None] = mapped_column(Text)
