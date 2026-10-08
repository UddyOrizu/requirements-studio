import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

import services.common.outbox  # noqa: F401
import services.gaps.db  # noqa: F401
import services.ideas.db  # noqa: F401
import services.identity_audit.db  # noqa: F401
import services.improve.db  # noqa: F401
import services.intake.db  # noqa: F401
import services.interviewer.db  # noqa: F401
import services.ir_store.db  # noqa: F401
import services.llm_gateway.db  # noqa: F401
from services.common.db import Base

# Every table in docs/04-data-model.md.
DOCS_04_TABLES = {
    "processes", "ir_versions", "ir_patches",
    "ideas", "suggestions", "story_refinements",
    "intake_sessions", "intake_turns",
    "sources", "source_blocks", "source_chunks", "pii_map",
    "extraction_runs", "gaps",
    "smes", "questions", "answers", "interviews",
    "stories_cache", "dor_reports", "signoffs", "waivers",
    "exports", "llm_calls", "audit_log", "events_outbox",
}


async def test_db_migration_creates_every_docs04_table(engine):
    async with engine.connect() as conn:
        tables = set(await conn.run_sync(lambda c: inspect(c).get_table_names()))
    assert tables - {"alembic_version"} == DOCS_04_TABLES


async def test_db_every_table_has_timestamps(engine):
    async with engine.connect() as conn:
        missing = await conn.run_sync(lambda c: [
            t for t in DOCS_04_TABLES
            if not {"created_at", "updated_at"} <= {col["name"] for col in inspect(c).get_columns(t)}
        ])
    assert missing == []


async def test_db_orm_models_match_migration(engine):
    """The ORM tables (M3, audit_log, events_outbox) must not drift from what the migration created."""
    async with engine.connect() as conn:
        diff = await conn.run_sync(lambda c: compare_metadata(
            MigrationContext.configure(c, opts={"include_object": _mapped_only}), Base.metadata))
    assert diff == []


def _mapped_only(obj, name, type_, reflected, compare_to):
    return not (type_ == "table" and reflected and compare_to is None)


@pytest.mark.parametrize("index", ["ix_source_chunks_embedding", "ix_smes_topic_embedding"])
async def test_db_vector_indexes_use_hnsw(engine, index):
    async with engine.connect() as conn:
        ddl = (await conn.execute(text("SELECT indexdef FROM pg_indexes WHERE indexname = :n"), {"n": index})).scalar()
    assert ddl and "USING hnsw" in ddl and "vector_cosine_ops" in ddl


async def test_db_open_gap_fingerprint_unique_until_resolved(sessionmaker):
    async with sessionmaker() as s:
        await s.execute(text("INSERT INTO processes (id, name, owner_user_id, status, variant) "
                             "VALUES ('proc_gap_test', 'p', 'u', 'draft', 'as_is')"))

        async def gap(gid: str, status: str):
            await s.execute(text(
                "INSERT INTO gaps (id, process_id, fingerprint, type, severity, detector, target_refs, title, "
                "why_it_matters, question, routing, priority, status, ir_version_detected) VALUES "
                "(:id, 'proc_gap_test', repeat('a', 40), 'node_without_actor', 'major', 'structural', "
                "'{/nodes/node_x}', 't', 'w', '{}', '{}', 1, :status, 1)"), {"id": gid, "status": status})

        await gap("gap_one", "resolved")
        await gap("gap_two", "open")  # a resolved gap does not block a new open one
        with pytest.raises(Exception, match="uq_gaps_process_id_fingerprint_unresolved"):
            async with s.begin_nested():
                await gap("gap_three", "open")
        await s.rollback()
