"""Internal users, approval requests and the email outbox.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-10

- users (roles user | admin; optional Entra ID link by object id), user_tokens (invitation and reset links, hashed).
- approval_requests: ask a named user to review a patch, sign off stories, decide a suggestion or answer a question.
- email_outbox: email queued with the change it announces, sent over SMTP with retries.
- questions: the person asked can be a user (assignee_user_id); sme_id becomes optional.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TABLES = ("users", "user_tokens", "approval_requests", "email_outbox")


def _timestamps() -> list[sa.Column]:
    return [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))]


def _ts(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("email", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("password_hash", sa.Text),
        sa.Column("entra_oid", sa.Text),
        sa.Column("session_version", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("failed_sign_ins", sa.Integer, nullable=False, server_default=sa.text("0")),
        _ts("locked_until"), _ts("last_sign_in_at"),
        sa.Column("created_by", sa.Text),
        *_timestamps(),
        sa.CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
        sa.CheckConstraint("status IN ('invited', 'active', 'disabled')", name="ck_users_status"),
    )
    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)
    op.create_index("uq_users_entra_oid", "users", ["entra_oid"], unique=True,
                    postgresql_where=sa.text("entra_oid IS NOT NULL"))

    op.create_table(
        "user_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Text, sa.ForeignKey("users.id", name="fk_user_tokens_user_id_users"), nullable=False),
        sa.Column("purpose", sa.Text, nullable=False),
        sa.Column("token_hash", sa.Text, nullable=False),
        _ts("expires_at", nullable=False), _ts("used_at"),
        sa.Column("created_by", sa.Text),
        *_timestamps(),
        sa.UniqueConstraint("token_hash", name="uq_user_tokens_token_hash"),
    )
    op.create_index("ix_user_tokens_user_id", "user_tokens", ["user_id"])

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("idea_id", sa.Text, sa.ForeignKey("ideas.id", name="fk_approval_requests_idea_id_ideas")),
        sa.Column("process_id", sa.Text,
                  sa.ForeignKey("processes.id", name="fk_approval_requests_process_id_processes")),
        sa.Column("subject_id", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("summary", sa.Text),
        sa.Column("message", sa.Text),
        sa.Column("details", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("requested_by", sa.Text, nullable=False),
        sa.Column("assignee_user_id", sa.Text,
                  sa.ForeignKey("users.id", name="fk_approval_requests_assignee_user_id_users"), nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default=sa.text("'pending'")),
        sa.Column("response", sa.Text),
        sa.Column("decided_by", sa.Text),
        _ts("decided_at"), _ts("due_at"),
        *_timestamps(),
        sa.CheckConstraint("kind IN ('patch_review', 'story_signoff', 'suggestion', 'question')",
                           name="ck_approval_requests_kind"),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'answered', 'cancelled', 'closed')",
                           name="ck_approval_requests_status"),
    )
    op.create_index("ix_approval_requests_assignee_status", "approval_requests", ["assignee_user_id", "status"])
    op.create_index("ix_approval_requests_requested_by_status", "approval_requests", ["requested_by", "status"])
    op.create_index("ix_approval_requests_subject", "approval_requests", ["kind", "subject_id"])
    op.create_index("uq_approval_requests_pending", "approval_requests", ["kind", "subject_id", "assignee_user_id"],
                    unique=True, postgresql_where=sa.text("status = 'pending'"))

    op.create_table(
        "email_outbox",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("to_address", sa.Text, nullable=False),
        sa.Column("to_name", sa.Text),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("text_body", sa.Text, nullable=False),
        sa.Column("html_body", sa.Text, nullable=False),
        sa.Column("template", sa.Text, nullable=False),
        sa.Column("related_id", sa.Text),
        sa.Column("status", sa.Text, nullable=False, server_default=sa.text("'queued'")),
        sa.Column("attempts", sa.Integer, nullable=False, server_default=sa.text("0")),
        _ts("next_attempt_at", nullable=False),
        sa.Column("last_error", sa.Text),
        _ts("sent_at"),
        *_timestamps(),
    )
    op.alter_column("email_outbox", "next_attempt_at", server_default=sa.text("now()"))
    op.create_index("ix_email_outbox_due", "email_outbox", ["next_attempt_at"],
                    postgresql_where=sa.text("status = 'queued'"))

    op.alter_column("questions", "sme_id", nullable=True)
    op.add_column("questions", sa.Column("assignee_user_id", sa.Text,
                                         sa.ForeignKey("users.id", name="fk_questions_assignee_user_id_users")))

    op.execute(f"""
    DO $$ BEGIN
      IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'rs_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON {', '.join(NEW_TABLES)} TO rs_app;
      END IF;
    END $$
    """)


def downgrade() -> None:
    op.drop_constraint("fk_questions_assignee_user_id_users", "questions", type_="foreignkey")
    op.drop_column("questions", "assignee_user_id")
    op.execute("DELETE FROM answers WHERE question_id IN (SELECT id FROM questions WHERE sme_id IS NULL)")
    op.execute("DELETE FROM questions WHERE sme_id IS NULL")
    op.alter_column("questions", "sme_id", nullable=False)
    for table in reversed(NEW_TABLES):
        op.drop_table(table)
