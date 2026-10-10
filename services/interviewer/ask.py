"""Ask a named person (M6): used by M0 "Not sure — ask someone" and by story detail "Ask someone" (M12).

Creates the question and the gap behind it, or marks an existing gap asked. The person is an internal user (or an
SME directory entry, matched to a user by email): they get an approval request of kind `question` by email and
answer in the app (record_answer). Automatic routing (S2) arrives in P9; until then the requester names the person.
"""
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gap_rules import fingerprint
from ir_core import Issue, PatchRejected
from services.common.events import EventEnvelope
from services.common.outbox import enqueue_event
from services.common.uuid7 import uuid7
from services.gaps.db import GapRow
from services.identity_audit.audit import write_audit
from services.identity_audit.db import User

from .db import Answer, Question, Sme

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


async def _person(s: AsyncSession, sme_id: str | None, user_id: str | None,
                  asked_by: str) -> tuple[Sme | None, User | None]:
    """The SME directory entry and/or the user to ask; either names the other through the email address."""
    if user_id:
        user = await s.get(User, user_id)
        if user is None or user.status == "disabled":
            raise PatchRejected([Issue("envelope", "/ask_user_id", f"unknown or disabled user {user_id}")])
        if user.id == asked_by:
            raise PatchRejected([Issue("envelope", "/ask_user_id", "choose someone other than yourself")])
        sme = (await s.execute(select(Sme).where(func.lower(Sme.email) == user.email.lower()))).scalars().first()
        return sme, user
    if not sme_id:
        raise PatchRejected([Issue("envelope", "/ask_user_id",
                                   "name the person to ask (automatic SME routing arrives with M6)")])
    sme = await s.get(Sme, sme_id)
    if sme is None:
        raise PatchRejected([Issue("envelope", "/ask_sme_id", f"unknown SME {sme_id}")])
    user = (await s.execute(select(User).where(func.lower(User.email) == sme.email.lower(),
                                               User.status != "disabled"))).scalar_one_or_none() if sme.email else None
    return sme, user


async def ask_someone(s: AsyncSession, *, process_id: str, ir_version: int, sme_id: str | None, asked_by: str,
                      text: str, context: str | None, answer_type: str, options: list[str], now,
                      existing_gap_id: str | None = None, new_gap: NewGap | None = None,
                      correlation_id: str, user_id: str | None = None) -> tuple[Question, GapRow, str]:
    """Returns (question, gap, captured line for the UI)."""
    sme, user = await _person(s, sme_id, user_id, asked_by)
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
                     routing={"topic_tags": [new_gap.topic],
                              "candidate_actor_ids": list(sme.actor_ids) if sme else []},
                     priority=4, status="asked", ir_version_detected=ir_version)
        s.add(gap)
    channel = "email" if user is not None or (sme and "email" in sme.channels) else "in_app"
    q = Question(id=f"q_{uuid7().hex}", process_id=process_id, origin="intake_ask_someone", asked_by=asked_by,
                 gap_ids=[gap.id], sme_id=sme.id if sme else None, assignee_user_id=user.id if user else None,
                 channel=channel, text=text[:400], context_snippet=(context or "")[:600], answer_type=answer_type,
                 suggested_answers=options, status="sent", sent_at=now, due_at=now + QUESTION_DUE)
    s.add(q)
    await s.flush()
    who = {"sme_id": sme.id if sme else None, "user_id": user.id if user else None}
    await enqueue_event(s, EventEnvelope(type="question.sent", process_id=process_id, correlation_id=correlation_id,
                                         payload={"question_id": q.id, **who}))
    await write_audit(s, actor_kind="user", actor_id=asked_by, action="question.sent", target=q.id,
                      process_id=process_id, after={**who, "gap_id": gap.id})
    if user is not None:
        from services.approvals.service import ApprovalService
        await ApprovalService(s, clock=lambda: now, correlation_id=correlation_id).for_question(
            question_id=q.id, process_id=process_id, asked_by=asked_by, assignee=user, text=q.text,
            context=q.context_snippet or None)
    name = user.name if user else sme.name
    title = sme.role_title if sme and sme.role_title else None
    role = f" ({title})" if title else ""
    return q, gap, f"Asked {name}{role}: {q.text}"


async def record_answer(s: AsyncSession, *, question_id: str, answered_by: str, answered_by_name: str, text: str,
                        now, correlation_id: str) -> Answer:
    """The person asked answers in the app. The answer is recorded and shown to the requester (conversation timeline
    and the story's open question); turning it into an IR change stays a patch the requester makes or accepts."""
    from services.ideas.db import Idea
    from services.intake.db import IntakeSession

    q = await s.get(Question, question_id, with_for_update=True)
    if q is None:
        raise PatchRejected([Issue("envelope", "/question_id", f"unknown question {question_id}")])
    answer = Answer(question_id=q.id, answered_by=answered_by, text=text.strip(), answered_at=now)
    s.add(answer)
    q.status = "answered"
    for gap_id in q.gap_ids:
        gap = await s.get(GapRow, (q.process_id, gap_id))
        if gap is not None and gap.status == "asked":
            gap.status = "answered"
    await s.flush()
    await enqueue_event(s, EventEnvelope(type="question.answered", process_id=q.process_id,
                                         correlation_id=correlation_id,
                                         payload={"question_id": q.id, "sme_id": q.sme_id, "user_id": answered_by}))
    await write_audit(s, actor_kind="user", actor_id=answered_by, action="question.answered", target=q.id,
                      process_id=q.process_id, after={"text": answer.text})
    idea = (await s.execute(select(Idea).where((Idea.as_is_process_id == q.process_id)
                                               | (Idea.to_be_process_id == q.process_id)))).scalars().first()
    sess = await s.get(IntakeSession, idea.session_id) if idea else None
    if sess is not None:
        from services.intake.service import IntakeService
        await IntakeService(s, None, clock=lambda: now, correlation_id=correlation_id).record_sme_answer(
            sess.id, question_id=q.id, patch_id=None, answered_by=answered_by, answer_text=answer.text,
            captured=[f"{answered_by_name or answered_by} answered: {answer.text}"[:500]])
    return answer
