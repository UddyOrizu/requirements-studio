"""gaps keyed by (process_id, id).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-08

Gap ids are only unique within a process: both sample processes have gap_story_priority, and an as-is and its to-be
share element ids. Nothing references gaps by foreign key (questions hold gap ids in an array).
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("pk_gaps", "gaps", type_="primary")
    op.create_primary_key("pk_gaps", "gaps", ["process_id", "id"])


def downgrade() -> None:
    op.drop_constraint("pk_gaps", "gaps", type_="primary")
    op.create_primary_key("pk_gaps", "gaps", ["id"])
