"""Processes belong to an idea as its as-is or to-be; the as-is freezes at fork; patch review reasons.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-08

- processes.idea_id + variant, unique per idea: an idea owns at most one as-is and one to-be (M11, M12).
- processes.frozen_at: set on the as-is when it is forked; the Patch Service refuses patches on a frozen process.
- ir_patches.review_reason: the reason given on reject (required) or edit-and-accept.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("processes", sa.Column("idea_id", sa.Text, sa.ForeignKey("ideas.id",
                                         name="fk_processes_idea_id_ideas"), nullable=True))
    op.add_column("processes", sa.Column("variant", sa.Text, nullable=False, server_default="as_is"))
    op.alter_column("processes", "variant", server_default=None)
    op.add_column("processes", sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("uq_processes_idea_id_variant", "processes", ["idea_id", "variant"], unique=True,
                    postgresql_where=sa.text("idea_id IS NOT NULL"))
    op.add_column("ir_patches", sa.Column("review_reason", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("ir_patches", "review_reason")
    op.drop_index("uq_processes_idea_id_variant", "processes")
    op.drop_column("processes", "frozen_at")
    op.drop_column("processes", "variant")
    op.drop_constraint("fk_processes_idea_id_ideas", "processes", type_="foreignkey")
    op.drop_column("processes", "idea_id")
