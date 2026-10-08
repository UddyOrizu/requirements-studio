"""suggestions.source: heuristic (from a candidate) or llm (an opportunity the heuristics missed).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-08
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("suggestions", sa.Column("source", sa.Text, nullable=False, server_default="heuristic"))
    op.alter_column("suggestions", "source", server_default=None)


def downgrade() -> None:
    op.drop_column("suggestions", "source")
