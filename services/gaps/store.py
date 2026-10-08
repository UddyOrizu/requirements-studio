"""Keep a process's stored gaps in step with the deterministic detectors (M5 Lifecycle: auto-resolve, dedupe).

The full M5 service (semantic pass, coverage gaps, debounced triggers) arrives in P8; M0 needs this much now.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gap_rules import detect_gaps, reconcile

from .db import GapRow


async def stored_gaps(session: AsyncSession, process_id: str) -> list[GapRow]:
    q = select(GapRow).where(GapRow.process_id == process_id).order_by(GapRow.created_at, GapRow.id)
    return list((await session.execute(q)).scalars())


async def sync_gaps(session: AsyncSession, ir: dict, *, patch_id: str | None, document_led: bool = False) -> list[dict]:
    """Detect, reconcile with what is stored, write the changes; returns every gap of the process (schema shape)."""
    rows = await stored_gaps(session, ir["process"]["id"])
    result = reconcile([r.as_gap() for r in rows], detect_gaps(ir, document_led=document_led), patch_id=patch_id)
    by_id = {r.id: r for r in rows}
    for g in result.resolved:
        by_id[g["gap_id"]].status, by_id[g["gap_id"]].resolved_by_patch_id = "resolved", patch_id
    for g in result.opened:
        row = GapRow(id=g["gap_id"], process_id=g["process_id"], fingerprint=g["fingerprint"], type=g["type"],
                     severity=g["severity"], detector=g["detector"], target_refs=g["target_refs"], title=g["title"],
                     why_it_matters=g["why_it_matters"], question=g["question"], routing=g["routing"],
                     priority=g["priority"], status="open", ir_version_detected=g["ir_version_detected"])
        session.add(row)
        rows.append(row)
    await session.flush()
    return [r.as_gap() for r in rows]
