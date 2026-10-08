"""ir_versions.snapshot as json, not jsonb.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-08

jsonb reorders object keys (shortest first), and the IR's maps are rendered in insertion order: goals, NFRs and
scope in the stories file, the "control not set" list. json keeps the document exactly as written. Snapshots are
read whole and never queried inside, so nothing is lost.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE ir_versions ALTER COLUMN snapshot TYPE json USING snapshot::json")


def downgrade() -> None:
    op.execute("ALTER TABLE ir_versions ALTER COLUMN snapshot TYPE jsonb USING snapshot::jsonb")
