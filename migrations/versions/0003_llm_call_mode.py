"""llm_calls.mode: live | record | replay, so replayed test calls never count as spend.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-08
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("llm_calls", sa.Column("mode", sa.Text, nullable=False, server_default="live"))
    op.alter_column("llm_calls", "mode", server_default=None)


def downgrade() -> None:
    op.drop_column("llm_calls", "mode")
