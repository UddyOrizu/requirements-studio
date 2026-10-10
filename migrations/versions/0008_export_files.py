"""Exports of files (M9 export screen) next to MOTHER packages.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-08

- idea_id, variant, formats, files (name, sha256, size, content type), draft, created_by.
- Uniqueness: a MOTHER package stays idempotent by (process, ir_hash, mode); a file export by (process, package_hash),
  because the same IR version can export different content after a sign-off or a gap changes.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("exports", sa.Column("idea_id", sa.Text, sa.ForeignKey("ideas.id", name="fk_exports_idea_id_ideas"),
                                       nullable=True))
    op.add_column("exports", sa.Column("variant", sa.Text, nullable=True))
    op.add_column("exports", sa.Column("formats", ARRAY(sa.Text), nullable=False,
                                       server_default=sa.text("'{}'::text[]")))
    op.add_column("exports", sa.Column("files", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("exports", sa.Column("draft", sa.Boolean, nullable=False, server_default=sa.false()))
    op.add_column("exports", sa.Column("created_by", sa.Text, nullable=True))
    op.drop_constraint("uq_exports_process_id_ir_hash_mode", "exports", type_="unique")
    op.create_index("uq_exports_process_id_ir_hash_mode", "exports", ["process_id", "ir_hash", "mode"], unique=True,
                    postgresql_where=sa.text("mode <> 'files'"))
    op.create_index("uq_exports_process_id_package_hash", "exports", ["process_id", "package_hash"], unique=True,
                    postgresql_where=sa.text("mode = 'files'"))


def downgrade() -> None:
    op.drop_index("uq_exports_process_id_package_hash", "exports")
    op.drop_index("uq_exports_process_id_ir_hash_mode", "exports")
    op.create_unique_constraint("uq_exports_process_id_ir_hash_mode", "exports", ["process_id", "ir_hash", "mode"])
    for column in ("created_by", "draft", "files", "formats", "variant"):
        op.drop_column("exports", column)
    op.drop_constraint("fk_exports_idea_id_ideas", "exports", type_="foreignkey")
    op.drop_column("exports", "idea_id")
