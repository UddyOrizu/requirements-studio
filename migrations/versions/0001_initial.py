"""Initial schema: every table in docs/04, pgvector, audit_log append-only, rs_app role.

Revision ID: 0001
Revises:
Create Date: 2026-10-08

Tables are declared here with plain sa.Table (not imported from app code) so this revision never changes when the
ORM does. Conventions (docs/04): UUIDv7 primary keys unless the doc gives a text id; created_at/updated_at on every
table; JSONB for structured columns. Element-id columns (proc_, src_, gap_, q_ …) are text.

Deviation from docs/04: every patch id column is text, because patch.schema.json makes patch_id a free string and the
KYC sample uses ids like `patch_kyc_asis_v1`. New patches get a UUIDv7 string.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copy of services.common.db.NAMING_CONVENTION.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
EMBEDDING_DIM = 1536

metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)
now = sa.text("now()")
TEXT_ARRAY = ARRAY(sa.Text)
EMPTY_TEXT_ARRAY = sa.text("'{}'::text[]")


def uuid_pk() -> sa.Column:
    return sa.Column("id", UUID(as_uuid=True), primary_key=True)


def text_pk() -> sa.Column:
    return sa.Column("id", sa.Text, primary_key=True)


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
    ]


def fk(name: str, target: str, nullable: bool = False, type_=sa.Text) -> sa.Column:
    return sa.Column(name, type_, sa.ForeignKey(target), nullable=nullable)


def col(name: str, type_=sa.Text, nullable: bool = False, **kw) -> sa.Column:
    return sa.Column(name, type_, nullable=nullable, **kw)


def opt(name: str, type_=sa.Text, **kw) -> sa.Column:
    return sa.Column(name, type_, nullable=True, **kw)


def ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


# ---------------------------------------------------------------- M3
sa.Table(
    "processes", metadata, text_pk(),
    col("name"), opt("domain"), opt("description"), col("owner_user_id"), col("status"),
    col("current_version", sa.Integer, server_default=sa.text("0")),
    col("settings", JSONB, server_default=sa.text("'{}'::jsonb")),  # thresholds, authority weights, auto_accept
    *timestamps(),
)
sa.Table(
    "ir_patches", metadata, text_pk(),
    fk("process_id", "processes.id"), col("base_version", sa.Integer), opt("applied_version", sa.Integer),
    col("ops", JSONB), col("author_kind"), col("author_id"), col("reason"), opt("evidence", JSONB),
    opt("interpretation_confidence", sa.Numeric), col("auto_apply", sa.Boolean), col("status"),
    opt("reviewed_by"), ts("reviewed_at", nullable=True), fk("supersedes_patch_id", "ir_patches.id", nullable=True),
    col("changed_paths", TEXT_ARRAY, server_default=EMPTY_TEXT_ARRAY),
    *timestamps(),
    sa.Index("ix_ir_patches_process_id_status", "process_id", "status"),
)
sa.Table(
    "ir_versions", metadata,
    sa.Column("process_id", sa.Text, sa.ForeignKey("processes.id"), primary_key=True),
    sa.Column("version", sa.Integer, primary_key=True),
    col("snapshot", JSONB), col("ir_hash", sa.CHAR(64)), fk("patch_id", "ir_patches.id", nullable=True),
    *timestamps(),
)

# ---------------------------------------------------------------- M12 / M11
sa.Table(
    "ideas", metadata, text_pk(),
    col("title"), col("summary"), col("owner_user_id"), col("status"), col("has_as_is", sa.Boolean),
    fk("as_is_process_id", "processes.id", nullable=True), fk("to_be_process_id", "processes.id", nullable=True),
    # No FK: the idea and its session are created together and each points at the other.
    col("session_id"),
    col("tags", TEXT_ARRAY, server_default=EMPTY_TEXT_ARRAY),
    col("stats", JSONB, server_default=sa.text("'{}'::jsonb")),
    *timestamps(),
)
sa.Table(
    "suggestions", metadata,
    sa.Column("id", sa.Text, primary_key=True),  # S01…
    sa.Column("idea_id", sa.Text, sa.ForeignKey("ideas.id"), primary_key=True),
    col("kind"), col("target_refs", TEXT_ARRAY), col("title"), col("change_summary"), col("rationale"),
    col("evidence", JSONB), col("benefit", JSONB), col("controls"), opt("risk"), col("confidence", sa.Numeric),
    col("status"), opt("decision", JSONB), col("ops", JSONB), fk("applied_patch_id", "ir_patches.id", nullable=True),
    *timestamps(),
)
sa.Table(
    "story_refinements", metadata, uuid_pk(),
    fk("process_id", "processes.id"), col("story_id"), col("instruction"), opt("preview", JSONB),
    fk("patch_id", "ir_patches.id", nullable=True), col("status"), col("by"), ts("at"),
    *timestamps(),
)

# ---------------------------------------------------------------- M6 (before M0: intake turns reference smes)
sa.Table(
    "smes", metadata, text_pk(),
    col("name"), col("email"), opt("role_title"),
    col("actor_ids", TEXT_ARRAY, server_default=EMPTY_TEXT_ARRAY),
    col("topic_tags", TEXT_ARRAY, server_default=EMPTY_TEXT_ARRAY),
    opt("topic_embedding", Vector(EMBEDDING_DIM)),
    col("process_ids_owned", TEXT_ARRAY, server_default=EMPTY_TEXT_ARRAY),
    col("channels", TEXT_ARRAY, server_default=EMPTY_TEXT_ARRAY),
    opt("max_open_questions", sa.Integer), opt("working_hours", JSONB), opt("out_of_office_until", sa.Date),
    fk("delegate_sme_id", "smes.id", nullable=True),
    *timestamps(),
    sa.Index("ix_smes_topic_embedding", "topic_embedding", postgresql_using="hnsw",
             postgresql_ops={"topic_embedding": "vector_cosine_ops"}),
)

# ---------------------------------------------------------------- M0
sa.Table(
    "intake_sessions", metadata, text_pk(),
    col("mode"), fk("idea_id", "ideas.id", nullable=True), fk("process_id", "processes.id"),
    col("requester_user_id"), col("phase"), col("status"),
    col("coverage", JSONB, server_default=sa.text("'{}'::jsonb")),
    col("parked", TEXT_ARRAY, server_default=EMPTY_TEXT_ARRAY), opt("current_target", JSONB),
    ts("started_at"), ts("completed_at", nullable=True),
    *timestamps(),
)
sa.Table(
    "intake_turns", metadata, uuid_pk(),
    fk("session_id", "intake_sessions.id"), col("n", sa.Integer), col("phase"), opt("target", JSONB),
    opt("question", JSONB), opt("answer_text"), opt("special"), fk("ask_sme_id", "smes.id", nullable=True),
    fk("patch_id", "ir_patches.id", nullable=True), opt("captured", JSONB), opt("assumptions", JSONB),
    opt("follow_up_question"), opt("coverage_after", JSONB), ts("at"),
    *timestamps(),
    sa.UniqueConstraint("session_id", "n"),
)

# ---------------------------------------------------------------- M1
sa.Table(
    "sources", metadata, text_pk(),
    fk("process_id", "processes.id"), col("kind"), col("title"), opt("uri"), col("sha256", sa.CHAR(64)),
    col("authority_weight", sa.Numeric), col("status"),
    col("metadata", JSONB, server_default=sa.text("'{}'::jsonb")), ts("deleted_at", nullable=True),
    *timestamps(),
    sa.UniqueConstraint("process_id", "sha256"),
)
sa.Table(
    "source_blocks", metadata, uuid_pk(),
    fk("source_id", "sources.id"), col("block_id"), col("ord", sa.Integer), col("text"), col("clean_text"),
    col("locator_kind"), col("locator_value"), opt("speaker"),
    col("heading_path", TEXT_ARRAY, server_default=EMPTY_TEXT_ARRAY),
    *timestamps(),
)
sa.Table(
    "source_chunks", metadata, uuid_pk(),
    fk("source_id", "sources.id"), col("ord", sa.Integer), col("block_ids", TEXT_ARRAY), col("text"),
    opt("embedding", Vector(EMBEDDING_DIM)),
    *timestamps(),
    sa.Index("ix_source_chunks_embedding", "embedding", postgresql_using="hnsw",
             postgresql_ops={"embedding": "vector_cosine_ops"}),
)
sa.Table(
    "pii_map", metadata, uuid_pk(),
    fk("source_id", "sources.id"), col("placeholder"), col("value_encrypted", sa.LargeBinary),
    *timestamps(),
)

# ---------------------------------------------------------------- M2
sa.Table(
    "extraction_runs", metadata, uuid_pk(),
    fk("process_id", "processes.id"), fk("source_id", "sources.id"), col("source_sha", sa.CHAR(64)),
    col("prompt_file"), col("prompt_sha256", sa.CHAR(64)), col("model"), col("status"), opt("stats", JSONB),
    fk("patch_id", "ir_patches.id", nullable=True),
    *timestamps(),
    sa.UniqueConstraint("source_id", "source_sha", "prompt_file", "prompt_sha256", "model"),
)

# ---------------------------------------------------------------- M5
sa.Table(
    "gaps", metadata, text_pk(),
    fk("process_id", "processes.id"), col("fingerprint", sa.CHAR(40)), col("type"), col("severity"),
    col("detector"), col("target_refs", TEXT_ARRAY), col("title"), col("why_it_matters"), col("question", JSONB),
    col("routing", JSONB), col("priority", sa.Numeric), col("status"), col("ir_version_detected", sa.Integer),
    fk("resolved_by_patch_id", "ir_patches.id", nullable=True), opt("waiver", JSONB),
    *timestamps(),
    sa.Index("uq_gaps_process_id_fingerprint_unresolved", "process_id", "fingerprint", unique=True,
             postgresql_where=sa.text("status NOT IN ('resolved')")),
    sa.Index("ix_gaps_process_id_status_priority", "process_id", "status", sa.text("priority DESC")),
)

# ---------------------------------------------------------------- M6
sa.Table(
    "questions", metadata, text_pk(),
    fk("process_id", "processes.id"), col("origin"), opt("asked_by"), col("gap_ids", TEXT_ARRAY),
    fk("sme_id", "smes.id"), opt("batch_id"), col("channel"), col("text"), opt("context_snippet"),
    col("answer_type"), opt("suggested_answers", JSONB), col("status"),
    ts("sent_at", nullable=True), ts("due_at", nullable=True), ts("reminded_at", nullable=True),
    ts("escalated_at", nullable=True),
    *timestamps(),
    sa.Index("ix_questions_sme_id_status", "sme_id", "status"),
)
sa.Table(
    "answers", metadata, uuid_pk(),
    fk("question_id", "questions.id"), col("answered_by"), col("text"), opt("structured_value", JSONB),
    ts("answered_at"), fk("patch_id", "ir_patches.id", nullable=True),
    opt("interpretation_confidence", sa.Numeric), opt("follow_up_question"),
    *timestamps(),
)
sa.Table(
    "interviews", metadata, uuid_pk(),
    fk("process_id", "processes.id"), col("participants", TEXT_ARRAY), col("gap_ids", TEXT_ARRAY),
    opt("transcript", JSONB), col("status"), fk("source_id", "sources.id", nullable=True),
    *timestamps(),
)

# ---------------------------------------------------------------- M7 / M8
sa.Table(
    "stories_cache", metadata,
    sa.Column("process_id", sa.Text, sa.ForeignKey("processes.id"), primary_key=True),
    sa.Column("ir_version", sa.Integer, primary_key=True),
    sa.Column("story_id", sa.Text, primary_key=True),
    col("rendered_md"), col("gherkin"),
    *timestamps(),
)
sa.Table(
    "dor_reports", metadata, uuid_pk(),
    fk("process_id", "processes.id"), col("ir_version", sa.Integer), col("report", JSONB),
    *timestamps(),
)
sa.Table(
    "signoffs", metadata, uuid_pk(),
    fk("process_id", "processes.id"), col("story_id"), col("ir_version", sa.Integer),
    col("closure_hash", sa.CHAR(64)), col("signed_by"), ts("signed_at"),
    *timestamps(),
)
sa.Table(
    "waivers", metadata, uuid_pk(),
    fk("process_id", "processes.id"), col("story_id"), col("check_id"), col("reason"), col("waived_by"),
    ts("waived_at"), ts("revoked_at", nullable=True),
    *timestamps(),
)

# ---------------------------------------------------------------- M9
sa.Table(
    "exports", metadata, uuid_pk(),
    fk("process_id", "processes.id"), col("ir_version", sa.Integer), col("ir_hash", sa.CHAR(64)),
    col("package_hash", sa.CHAR(64)), col("mode"), opt("uri"), col("status"), opt("mother_import_id"),
    fk("superseded_by", "exports.id", nullable=True, type_=UUID(as_uuid=True)),
    *timestamps(),
    sa.UniqueConstraint("process_id", "ir_hash", "mode"),
)

# ---------------------------------------------------------------- Shared
sa.Table(
    "llm_calls", metadata, uuid_pk(),
    col("correlation_id"), fk("process_id", "processes.id", nullable=True), col("prompt_file"),
    col("prompt_sha256", sa.CHAR(64)), col("model"), opt("input_tokens", sa.Integer),
    opt("output_tokens", sa.Integer), opt("latency_ms", sa.Integer), col("status"), opt("error"),
    *timestamps(),
)
sa.Table(
    "audit_log", metadata, uuid_pk(),
    opt("process_id"),  # no FK: audit rows outlive what they describe
    col("actor_kind"), col("actor_id"), col("action"), col("target"), opt("before", JSONB), opt("after", JSONB),
    col("at", sa.DateTime(timezone=True), server_default=now),
    *timestamps(),
    sa.Index("ix_audit_log_process_id_at", "process_id", "at"),
)
sa.Table(
    "events_outbox", metadata, uuid_pk(),
    col("type"), col("payload", JSONB), ts("published_at", nullable=True),
    *timestamps(),
    sa.Index("ix_events_outbox_unpublished", "created_at", postgresql_where=sa.text("published_at IS NULL")),
)

# asyncpg runs one statement per execute, so each is its own string.
APPEND_ONLY_SQL = [
    """
    CREATE FUNCTION audit_log_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      RAISE EXCEPTION 'audit_log is append-only (% rejected)', TG_OP USING ERRCODE = 'insufficient_privilege';
    END $$
    """,
    "CREATE TRIGGER audit_log_no_update_delete BEFORE UPDATE OR DELETE ON audit_log "
    "FOR EACH ROW EXECUTE FUNCTION audit_log_append_only()",
    "CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log "
    "FOR EACH STATEMENT EXECUTE FUNCTION audit_log_append_only()",
]

# rs_app is the role the application's login user is granted. It is NOLOGIN and cluster-wide, so downgrade leaves it.
APP_ROLE_SQL = [
    """
    DO $$ BEGIN
      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rs_app') THEN CREATE ROLE rs_app NOLOGIN; END IF;
    END $$
    """,
    "GRANT USAGE ON SCHEMA public TO rs_app",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rs_app",
    "REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM rs_app",
]


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    metadata.create_all(bind)
    for sql in APPEND_ONLY_SQL + APP_ROLE_SQL:
        op.execute(sql)


def downgrade() -> None:
    bind = op.get_bind()
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM rs_app")
    op.execute("REVOKE USAGE ON SCHEMA public FROM rs_app")
    metadata.drop_all(bind)
    op.execute("DROP FUNCTION IF EXISTS audit_log_append_only()")
