from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .db import AuditLog


async def write_audit(
    session: AsyncSession,
    *,
    actor_kind: str,
    actor_id: str,
    action: str,
    target: str,
    process_id: str | None = None,
    before: Any = None,
    after: Any = None,
) -> AuditLog:
    """Record a state change in the caller's transaction, so the audit row commits or rolls back with it."""
    row = AuditLog(process_id=process_id, actor_kind=actor_kind, actor_id=actor_id, action=action, target=target,
                   before=before, after=after)
    session.add(row)
    await session.flush()
    return row
