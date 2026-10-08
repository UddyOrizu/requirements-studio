"""M3 tables: processes, ir_versions, ir_patches (docs/04). Only the Patch Service writes ir_versions."""
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ARRAY, CHAR, DateTime, ForeignKey, Index, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from services.common.db import Base, Timestamps
from services.common.uuid7 import uuid7_str


class Process(Timestamps, Base):
    __tablename__ = "processes"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # proc_… (IR process.id)
    name: Mapped[str] = mapped_column(Text)
    domain: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    owner_user_id: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    current_version: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    # thresholds, authority weights, auto_accept policy
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class IrPatch(Timestamps, Base):
    __tablename__ = "ir_patches"
    __table_args__ = (Index("ix_ir_patches_process_id_status", "process_id", "status"),)

    # Text, not uuid: patch_id is a free string in patch.schema.json and samples use ids like patch_kyc_asis_v1.
    id: Mapped[str] = mapped_column(Text, primary_key=True, default=uuid7_str)
    process_id: Mapped[str] = mapped_column(ForeignKey("processes.id"))
    base_version: Mapped[int] = mapped_column(Integer)
    applied_version: Mapped[int | None] = mapped_column(Integer)
    ops: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    author_kind: Mapped[str] = mapped_column(Text)
    author_id: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    interpretation_confidence: Mapped[Decimal | None] = mapped_column(Numeric)
    auto_apply: Mapped[bool]
    status: Mapped[str] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supersedes_patch_id: Mapped[str | None] = mapped_column(ForeignKey("ir_patches.id"))
    changed_paths: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))


class IrVersion(Timestamps, Base):
    __tablename__ = "ir_versions"

    process_id: Mapped[str] = mapped_column(ForeignKey("processes.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    ir_hash: Mapped[str] = mapped_column(CHAR(64))  # ir_core.ir_hash(snapshot)
    patch_id: Mapped[str | None] = mapped_column(ForeignKey("ir_patches.id"))
