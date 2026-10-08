"""Ask a named SME (M6): used by M0 "Not sure — ask someone" and by story detail "Ask someone" (M12).

Creates the question (email or portal; no Teams yet) and the gap behind it, or marks an existing gap asked.
Automatic routing and delivery (S2) arrive in P9; until then the requester names the person.
"""
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from gap_rules import fingerprint
from ir_core import Issue, PatchRejected
from services.common.events import EventEnvelope
from services.common.outbox import enqueue_event
from services.common.uuid7 import uuid7
from services.gaps.db import GapRow
from services.identity_audit.audit import write_audit

from .db import Question, Sme

QUESTION_DUE = timedelta(days=2)


@dataclass
class NewGap:
    """The gap to open when the question is not about an existing one."""

    gap_id: str
    type: str
    target_refs: list[str]
    title: str
    why_it_matters: str
    topic: str


async def ask_someone(s: AsyncSession, *, process_id: str, ir_version: int, sme_id: str | None, asked_by: str,
                      text: str, context: str | None, answer_type: str, options: list[str], now,
                      existing_gap_id: str | None = None, new_gap: NewGap | None = None,
                      correlation_id: str) -> tuple[Question, GapRow, str]:
    """Returns (question, gap, captured line for the UI)."""
    if not sme_id:
        raise PatchRejected([Issue("envelope", "/ask_sme_id",
                                   "name the person to ask (automatic SME routing arrives with M6)")])
    sme = await s.get(Sme, sme_id)
    if sme is None:
        raise PatchRejected([Issue("envelope", "/ask_sme_id", f"unknown SME {sme_id}")])
    answer_type = {"multi_choice": "choice"}.get(answer_type, answer_type) or "free_text"
    gap = await s.get(GapRow, (process_id, existing_gap_id)) if existing_gap_id else None
    if gap is not None:
        gap.status = "asked"
    else:
        gap = GapRow(id=new_gap.gap_id[:64], process_id=process_id,
                     fingerprint=fingerprint(new_gap.type, new_gap.target_refs), type=new_gap.type,
                     severity="major", detector="intake", target_refs=new_gap.target_refs,
                     title=new_gap.title[:200], why_it_matters=new_gap.why_it_matters,
                     question={"text": text, "answer_type": answer_type, "suggested_answers": options},
                     routing={"topic_tags": [new_gap.topic], "candidate_actor_ids": list(sme.actor_ids)},
                     priority=4, status="asked", ir_version_detected=ir_version)
        s.add(gap)
    q = Question(id=f"q_{uuid7().hex}", process_id=process_id, origin="intake_ask_someone", asked_by=asked_by,
                 gap_ids=[gap.id], sme_id=sme.id, channel="email" if "email" in sme.channels else "in_app",
                 text=text[:400], context_snippet=(context or "")[:600], answer_type=answer_type,
                 suggested_answers=options, status="sent", sent_at=now, due_at=now + QUESTION_DUE)
    s.add(q)
    await s.flush()
    await enqueue_event(s, EventEnvelope(type="question.sent", process_id=process_id, correlation_id=correlation_id,
                                         payload={"question_id": q.id, "sme_id": sme.id}))
    await write_audit(s, actor_kind="user", actor_id=asked_by, action="question.sent", target=q.id,
                      process_id=process_id, after={"sme_id": sme.id, "gap_id": gap.id})
    role = f" ({sme.role_title})" if sme.role_title else ""
    return q, gap, f"Asked {sme.name}{role}: {q.text}"
