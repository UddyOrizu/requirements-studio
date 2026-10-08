import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from services.common.events import EventEnvelope
from services.common.outbox import EventOutbox, enqueue_event
from services.identity_audit.audit import write_audit
from services.identity_audit.db import AuditLog


async def _audit(s, target: str) -> AuditLog:
    return await write_audit(s, actor_kind="user", actor_id="user_test", action="patch.applied", target=target,
                             process_id="proc_audit_test", before={"v": 1}, after={"v": 2})


async def test_db_audit_log_insert(sessionmaker):
    async with sessionmaker() as s:
        row = await _audit(s, "patch_insert")
        await s.commit()
    async with sessionmaker() as s:
        got = await s.get(AuditLog, row.id)
        assert got.action == "patch.applied" and got.after == {"v": 2} and got.at is not None
        assert row.id.version == 7


@pytest.mark.parametrize("sql", [
    "UPDATE audit_log SET action = 'tampered'",
    "DELETE FROM audit_log",
    "TRUNCATE audit_log",
])
async def test_db_audit_log_is_append_only(sessionmaker, sql):
    async with sessionmaker() as s:
        await _audit(s, "patch_append_only")
        await s.commit()
    async with sessionmaker() as s:
        with pytest.raises(DBAPIError, match="append-only"):
            await s.execute(text(sql))


@pytest.mark.parametrize("sql", ["UPDATE audit_log SET action = 'x'", "DELETE FROM audit_log"])
async def test_db_app_role_lacks_update_delete_on_audit_log(sessionmaker, sql):
    async with sessionmaker() as s:
        await s.execute(text("SET LOCAL ROLE rs_app"))
        await _audit(s, "patch_as_app_role")  # INSERT is allowed
        with pytest.raises(DBAPIError, match="permission denied"):
            await s.execute(text(sql))


async def test_db_audit_and_outbox_commit_together(sessionmaker):
    event = EventEnvelope(type="ir.patched", process_id="proc_audit_test", ir_version=4, correlation_id="corr-1",
                          payload={"patch_id": "p1", "from_version": 3, "to_version": 4, "changed_paths": ["/nodes"]})
    async with sessionmaker() as s:
        audit = await _audit(s, "patch_commit")
        await enqueue_event(s, event)
        await s.commit()
    async with sessionmaker() as s:
        assert await s.get(AuditLog, audit.id) is not None
        row = await s.get(EventOutbox, event.event_id)
        assert row.type == "ir.patched" and row.published_at is None
        assert EventEnvelope.model_validate(row.payload) == event


async def test_db_audit_and_outbox_roll_back_together(sessionmaker):
    event = EventEnvelope(type="patch.proposed", process_id=None, correlation_id="corr-2",
                          payload={"patch_id": "p2", "author": "agent:x", "reviewer_ids": []})
    async with sessionmaker() as s:
        audit = await _audit(s, "patch_rollback")
        await enqueue_event(s, event)
        await s.rollback()
    async with sessionmaker() as s:
        assert await s.get(AuditLog, audit.id) is None
        assert (await s.execute(select(EventOutbox).where(EventOutbox.id == event.event_id))).first() is None
