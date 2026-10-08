"""Intake timeline entries beyond turns, and session state.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-08

intake_turns holds every timeline entry of a session (schemas/intake-session.schema.json `timeline`), not only
requester turns: `kind` (turn, playback, phase_change, fork, system_patch, sme_answer, signoff, …), the `turn` label
(T7), which process it applies to, and the rest of the entry in `payload`. `undone_by_patch_id` marks undone turns.
intake_sessions gains the intake source id and `state` (follow-up, confirmed playbacks, requester details).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("intake_turns", sa.Column("kind", sa.Text, nullable=False, server_default="turn"))
    op.alter_column("intake_turns", "kind", server_default=None)
    op.add_column("intake_turns", sa.Column("turn", sa.Text, nullable=True))
    op.add_column("intake_turns", sa.Column("process_variant", sa.Text, nullable=True))
    op.add_column("intake_turns", sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("intake_turns", sa.Column("undone_by_patch_id", sa.Text, sa.ForeignKey(
        "ir_patches.id", name="fk_intake_turns_undone_by_patch_id_ir_patches"), nullable=True))
    op.add_column("intake_sessions", sa.Column("source_id", sa.Text, nullable=True))
    op.add_column("intake_sessions", sa.Column("state", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")))


def downgrade() -> None:
    op.drop_column("intake_sessions", "state")
    op.drop_column("intake_sessions", "source_id")
    op.drop_constraint("fk_intake_turns_undone_by_patch_id_ir_patches", "intake_turns", type_="foreignkey")
    for column in ("undone_by_patch_id", "payload", "process_variant", "turn", "kind"):
        op.drop_column("intake_turns", column)
