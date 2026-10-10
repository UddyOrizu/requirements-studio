"""Approval requests (docs/03 §1 Approvals).

Someone who may decide a thing (the idea's owner, an admin, or for a proposed change also its author) asks a named
user to decide it instead: approve or reject a proposed IR change (M3), sign off the stories (M8), accept or reject
an improvement suggestion (M11), or answer a question ("ask someone", M6). The assignee gets an email with a link and
decides in the app; the decision runs through the owning service exactly as if the owner had made it (patches stay
the only way the IR changes). The requester is emailed the outcome.
"""
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.db import utcnow
from services.common.errors import Forbidden, InvalidInput
from services.common.events import EventEnvelope
from services.common.outbox import enqueue_event
from services.common.settings import get_settings
from services.common.uuid7 import uuid7
from services.ideas.db import Idea
from services.identity_audit.audit import write_audit
from services.identity_audit.auth import Principal
from services.identity_audit.db import User
from services.ir_store.service import Actor, Conflict, NotFound, PatchService
from services.notifications import queue_email

from .db import ApprovalRequest

KINDS = ("patch_review", "story_signoff", "suggestion", "question")
DUE = timedelta(days=3)


@dataclass(frozen=True)
class Wording:
    verb: str  # subject: "<requester> asks you to <verb>: <title>"
    ask: str  # body: "<requester> asks you to <ask> for "<idea>"."
    action: str  # "Open it in Requirements Studio to <action>"
    label: str  # email button


WORDING = {
    "patch_review": Wording("review a change", "review a proposed change", "approve or reject it",
                            "Review the change"),
    "story_signoff": Wording("sign off", "sign off the user stories", "sign them off or ask for changes",
                             "Review the stories"),
    "suggestion": Wording("decide an improvement", "accept or reject an improvement suggestion", "decide",
                          "Review the suggestion"),
    "question": Wording("answer a question", "answer a question", "answer it", "Answer the question"),
}
OUTCOME = {"approved": "approved", "rejected": "rejected", "answered": "answered"}


class ApprovalService:
    def __init__(self, session: AsyncSession, llm=None, *, clock=utcnow, correlation_id: str | None = None,
                 web_base_url: str | None = None):
        self.s, self.llm, self.clock = session, llm, clock
        self.correlation_id = correlation_id or str(uuid7())
        self.web = (web_base_url or get_settings().web_base_url).rstrip("/")
        self.patches = PatchService(session, clock=clock, correlation_id=self.correlation_id)

    # ================================================================== requests
    async def request(self, kind: str, *, actor: Principal, assignee_user_id: str, subject_id: str,
                      idea_id: str | None = None, message: str | None = None) -> ApprovalRequest:
        """Ask `assignee_user_id` to decide something `actor` may decide. Idempotent per (kind, subject, person)."""
        if kind not in KINDS or kind == "question":
            raise InvalidInput("/kind", "kind must be patch_review, story_signoff or suggestion (questions are "
                                        "asked with 'ask someone')")
        assignee = await self._assignee(assignee_user_id, actor.user_id)
        prepare = {"patch_review": self._patch_subject, "story_signoff": self._signoff_subject,
                   "suggestion": self._suggestion_subject}[kind]
        subject = await prepare(actor, subject_id, idea_id)
        return await self._create(kind, actor.user_id, assignee, message=message, **subject)

    async def for_question(self, *, question_id: str, process_id: str, asked_by: str, assignee: User, text: str,
                           context: str | None) -> ApprovalRequest:
        """"Ask someone" (M0 and story detail): the person asked is an internal user → email them the question."""
        idea = (await self.s.execute(select(Idea).where(
            (Idea.as_is_process_id == process_id) | (Idea.to_be_process_id == process_id)))).scalars().first()
        return await self._create("question", asked_by, assignee, subject_id=question_id, process_id=process_id,
                                  idea_id=idea.id if idea else None, title=text, summary=context, message=None,
                                  details={"answer_type": "free_text"})

    async def _create(self, kind: str, requested_by: str, assignee: User, *, subject_id: str, title: str,
                      process_id: str | None, idea_id: str | None, summary: str | None, message: str | None,
                      details: dict[str, Any]) -> ApprovalRequest:
        existing = (await self.s.execute(select(ApprovalRequest).where(
            ApprovalRequest.kind == kind, ApprovalRequest.subject_id == subject_id,
            ApprovalRequest.assignee_user_id == assignee.id, ApprovalRequest.status == "pending"))).scalar_one_or_none()
        if existing is not None:
            return existing
        now = self.clock()
        row = ApprovalRequest(id=f"apr_{uuid7().hex}", kind=kind, idea_id=idea_id, process_id=process_id,
                              subject_id=subject_id, title=title[:300], summary=(summary or None) and summary[:1000],
                              message=(message or "").strip()[:1000] or None, details=details,
                              requested_by=requested_by, assignee_user_id=assignee.id, status="pending",
                              due_at=now + DUE)
        self.s.add(row)
        await self.s.flush()
        await write_audit(self.s, actor_kind="user", actor_id=requested_by, action="approval.requested",
                          target=row.id, process_id=process_id,
                          after={"kind": kind, "subject_id": subject_id, "assignee": assignee.id})
        await enqueue_event(self.s, EventEnvelope(
            type="approval.requested", process_id=process_id, correlation_id=self.correlation_id,
            payload={"approval_id": row.id, "kind": kind, "subject_id": subject_id, "assignee_user_id": assignee.id,
                     "requested_by": requested_by}))
        words = WORDING[kind]
        await queue_email(self.s, to_address=assignee.email, to_name=assignee.name, template="approval_request",
                          related_id=row.id, context={
                              "requester_name": await self._name(requested_by), "verb": words.verb,
                              "ask": words.ask, "action": words.action, "action_label": words.label,
                              "idea_title": await self._idea_title(idea_id), "title": row.title,
                              "summary": row.summary or "", "message": row.message or "", "link": self._link(row)})
        return row

    async def _assignee(self, user_id: str, requester_id: str) -> User:
        user = await self.s.get(User, user_id)
        if user is None:
            raise InvalidInput("/assignee_user_id", f"unknown user {user_id}")
        if user.status == "disabled":
            raise InvalidInput("/assignee_user_id", f"{user.name}'s account is disabled")
        if user.id == requester_id:
            raise InvalidInput("/assignee_user_id", "choose someone other than yourself")
        return user

    # ------------------------------------------------------------------ subjects
    async def _patch_subject(self, actor: Principal, patch_id: str, idea_id: str | None) -> dict:
        row = await self.patches.get_patch(patch_id)
        proc = await self.patches.get_process(row.process_id)
        if not (actor.is_admin or actor.user_id in (proc.owner_user_id, row.author_id)):
            raise Forbidden("only the process owner, the change's author or an admin can ask for a review")
        if row.status != "proposed":
            raise Conflict("/problems/patch-not-proposed", f"patch {patch_id} is {row.status}",
                           patch_status=row.status)
        n = len(row.ops)
        return {"subject_id": row.id, "process_id": proc.id, "idea_id": proc.idea_id, "title": row.reason,
                "summary": f"{n} change{'s' if n != 1 else ''} to {proc.name}",
                "details": {"process_name": proc.name, "changed_paths": list(row.changed_paths or []),
                            "base_version": row.base_version}}

    async def _signoff_subject(self, actor: Principal, session_id: str, idea_id: str | None) -> dict:
        from services.intake.service import IntakeService
        from story_renderer import derive_stories
        intake = IntakeService(self.s, self.llm, clock=self.clock, correlation_id=self.correlation_id)
        sess = await intake._session(session_id)
        idea = await self.s.get(Idea, sess.idea_id) if sess.idea_id else None
        owner = idea.owner_user_id if idea else sess.requester_user_id
        if not (actor.is_admin or actor.user_id == owner):
            raise Forbidden("only the idea's owner or an admin can ask for a sign-off")
        if sess.phase != "validate" or (sess.current_target or {}).get("kind") != "signoff":
            raise Conflict("/problems/not-ready-for-signoff",
                           "ask for a sign-off once the conversation reaches sign-off in Validate")
        ir = await self.patches.get_ir(sess.process_id)
        stories = derive_stories(ir, [])
        version = ir["process"]["version"]
        n = len(stories)
        return {"subject_id": sess.id, "process_id": sess.process_id, "idea_id": sess.idea_id,
                "title": f"{n} user stor{'ies' if n != 1 else 'y'} for {idea.title if idea else ir['process']['name']}",
                "summary": f"{ir['process']['variant'].replace('_', '-')} version {version}",
                "details": {"ir_version": version, "story_ids": sorted(stories)}}

    async def _suggestion_subject(self, actor: Principal, sid: str, idea_id: str | None) -> dict:
        from services.improve.service import ImproveService
        if not idea_id:
            raise InvalidInput("/idea_id", "a suggestion is addressed through its idea")
        improve = ImproveService(self.s, self.llm, clock=self.clock, correlation_id=self.correlation_id)
        idea = await improve._idea(idea_id)
        if not (actor.is_admin or actor.user_id == idea.owner_user_id):
            raise Forbidden("only the idea's owner or an admin can send a suggestion for a decision")
        row = await improve._row(idea_id, sid, lock=False)
        return {"subject_id": sid, "process_id": idea.to_be_process_id, "idea_id": idea_id,
                "title": f"{sid}: {row.title}", "summary": row.change_summary,
                "details": {"benefit": row.benefit, "kind": row.kind}}

    # ================================================================== decisions
    async def decide(self, approval_id: str, *, actor: Principal, decision: str,
                     note: str | None = None) -> ApprovalRequest:
        row = await self._get(approval_id, lock=True)
        if row.status != "pending":
            raise Conflict("/problems/approval-closed", f"this request is already {row.status}", status_now=row.status)
        if actor.user_id != row.assignee_user_id:
            raise Forbidden("only the person this was sent to can decide it")
        note = (note or "").strip() or None
        allowed = ("answer",) if row.kind == "question" else ("approve", "reject")
        if decision not in allowed:
            raise InvalidInput("/decision", f"decision must be {' or '.join(allowed)}")
        if decision in ("reject", "answer") and not note:
            raise InvalidInput("/note", "write your answer" if decision == "answer" else
                               "say what needs to change (a short note is required to reject)")
        me = Actor("user", actor.user_id)
        await {"patch_review": self._decide_patch, "story_signoff": self._decide_signoff,
               "suggestion": self._decide_suggestion, "question": self._decide_question}[row.kind](
            row, me, actor, decision, note)
        row.status = {"approve": "approved", "reject": "rejected", "answer": "answered"}[decision]
        row.response, row.decided_by, row.decided_at = note, actor.user_id, self.clock()
        await self._closed(row, actor.user_id)
        await self.s.flush()
        await write_audit(self.s, actor_kind="user", actor_id=actor.user_id, action="approval.decided", target=row.id,
                          process_id=row.process_id, after={"status": row.status, "note": note})
        await enqueue_event(self.s, EventEnvelope(
            type="approval.decided", process_id=row.process_id, correlation_id=self.correlation_id,
            payload={"approval_id": row.id, "kind": row.kind, "subject_id": row.subject_id, "status": row.status,
                     "decided_by": actor.user_id}))
        requester = await self.s.get(User, row.requested_by)
        if requester is not None and requester.status != "disabled":
            await queue_email(self.s, to_address=requester.email, to_name=requester.name,
                              template="approval_decided", related_id=row.id, context={
                                  "assignee_name": actor.name or actor.user_id, "outcome": OUTCOME[row.status],
                                  "title": row.title, "note": note or "", "link": self._link(row),
                                  "idea_title": await self._idea_title(row.idea_id), "action_label": "Open"})
        return row

    async def _decide_patch(self, row, me: Actor, actor: Principal, decision: str, note: str | None) -> None:
        if decision == "approve":
            result = await self.patches.accept(row.subject_id, reviewer=me, reason=note)
            if result.status != "applied":
                raise Conflict("/problems/patch-conflict",
                               "newer changes touch the same elements; this change cannot be applied",
                               conflicting_paths=result.conflicting_paths)
        else:
            await self.patches.reject(row.subject_id, reviewer=me, reason=note)

    async def _decide_signoff(self, row, me: Actor, actor: Principal, decision: str, note: str | None) -> None:
        if decision != "approve":
            return  # the requester reads the note; nothing changes until they ask again
        from services.intake.service import IntakeService
        intake = IntakeService(self.s, self.llm, clock=self.clock, correlation_id=self.correlation_id)
        sess = await intake._session(row.subject_id)
        current = (await self.patches.get_process(sess.process_id)).current_version
        if current != row.details.get("ir_version"):
            raise Conflict("/problems/stories-changed", "the stories changed after this request; ask the owner to "
                                                        "send it again", requested_version=row.details.get(
                                                            "ir_version"), current_version=current)
        await intake.sign_off(row.subject_id, user_id=actor.user_id, signer_name=actor.name)

    async def _decide_suggestion(self, row, me: Actor, actor: Principal, decision: str, note: str | None) -> None:
        from services.improve.service import ImproveService
        improve = ImproveService(self.s, self.llm, clock=self.clock, correlation_id=self.correlation_id)
        if decision == "approve":
            await improve.accept(row.idea_id, row.subject_id, user_id=actor.user_id)
        else:
            await improve.reject(row.idea_id, row.subject_id, user_id=actor.user_id, reason=note)

    async def _decide_question(self, row, me: Actor, actor: Principal, decision: str, note: str | None) -> None:
        from services.interviewer.ask import record_answer
        await record_answer(self.s, question_id=row.subject_id, answered_by=actor.user_id,
                            answered_by_name=actor.name, text=note, now=self.clock(),
                            correlation_id=self.correlation_id)

    async def cancel(self, approval_id: str, *, actor: Principal) -> ApprovalRequest:
        row = await self._get(approval_id, lock=True)
        if not (actor.is_admin or actor.user_id == row.requested_by):
            raise Forbidden("only the person who asked (or an admin) can withdraw a request")
        if row.status != "pending":
            raise Conflict("/problems/approval-closed", f"this request is already {row.status}", status_now=row.status)
        row.status, row.decided_by, row.decided_at = "cancelled", actor.user_id, self.clock()
        await write_audit(self.s, actor_kind="user", actor_id=actor.user_id, action="approval.cancelled",
                          target=row.id, process_id=row.process_id)
        await self.s.flush()
        return row

    async def settle(self, kind: str, subject_id: str, *, by: str, idea_id: str | None = None) -> int:
        """The subject was decided directly (the owner accepted the patch, decided the suggestion, signed off):
        close the pending requests about it. Returns how many."""
        q = select(ApprovalRequest).where(ApprovalRequest.kind == kind, ApprovalRequest.subject_id == subject_id,
                                          ApprovalRequest.status == "pending")
        if idea_id:
            q = q.where(ApprovalRequest.idea_id == idea_id)
        rows = list((await self.s.execute(q.with_for_update())).scalars())
        for row in rows:
            row.status, row.decided_by, row.decided_at = "closed", by, self.clock()
            row.response = f"Decided directly by {await self._name(by)}"
            await write_audit(self.s, actor_kind="user", actor_id=by, action="approval.closed", target=row.id,
                              process_id=row.process_id)
        await self.s.flush()
        return len(rows)

    async def _closed(self, decided: ApprovalRequest, by: str) -> None:
        """The same thing was sent to several people: once one decides, the others' requests close."""
        others = await self.s.execute(select(ApprovalRequest).where(
            ApprovalRequest.kind == decided.kind, ApprovalRequest.subject_id == decided.subject_id,
            ApprovalRequest.idea_id.is_not_distinct_from(decided.idea_id), ApprovalRequest.status == "pending",
            ApprovalRequest.id != decided.id).with_for_update())
        for row in others.scalars():
            row.status, row.decided_by, row.decided_at = "closed", by, self.clock()
            row.response = f"Decided by {await self._name(by)}"

    # ================================================================== reads
    async def _get(self, approval_id: str, *, lock: bool = False) -> ApprovalRequest:
        row = await self.s.get(ApprovalRequest, approval_id, with_for_update=lock)
        if row is None:
            raise NotFound(f"approval request {approval_id} not found")
        return row

    async def inbox(self, actor: Principal, *, box: str = "inbox", status: str | None = "pending",
                   idea_id: str | None = None) -> list[dict]:
        q = select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc())
        if box == "inbox":
            q = q.where(ApprovalRequest.assignee_user_id == actor.user_id)
        elif box == "sent":
            q = q.where(ApprovalRequest.requested_by == actor.user_id)
        elif not actor.is_admin and not idea_id:
            raise Forbidden("only an administrator can list every request")
        if status:
            q = q.where(ApprovalRequest.status == status)
        if idea_id:
            q = q.where(ApprovalRequest.idea_id == idea_id)
        names: dict[str, str] = {}
        return [await self._summary(r, names) for r in (await self.s.execute(q.limit(200))).scalars()]

    async def counts(self, actor: Principal) -> dict:
        rows = await self.s.execute(select(ApprovalRequest.id).where(
            ApprovalRequest.assignee_user_id == actor.user_id, ApprovalRequest.status == "pending"))
        return {"pending": len(rows.all())}

    async def detail(self, approval_id: str, actor: Principal) -> dict:
        row = await self._get(approval_id)
        if not (actor.is_admin or actor.user_id in (row.assignee_user_id, row.requested_by)):
            raise Forbidden("this request was not sent to you")
        out = await self._summary(row, {})
        out["subject"] = await self._subject_view(row)
        out["can_decide"] = row.status == "pending" and actor.user_id == row.assignee_user_id
        out["can_cancel"] = row.status == "pending" and (actor.is_admin or actor.user_id == row.requested_by)
        return out

    async def _summary(self, row: ApprovalRequest, names: dict[str, str]) -> dict:
        async def name(uid: str | None) -> str | None:
            if uid is None:
                return None
            if uid not in names:
                names[uid] = await self._name(uid)
            return names[uid]

        return {"approval_id": row.id, "kind": row.kind, "status": row.status, "title": row.title,
                "summary": row.summary, "message": row.message, "response": row.response,
                "idea_id": row.idea_id, "idea_title": await self._idea_title(row.idea_id),
                "process_id": row.process_id, "subject_id": row.subject_id, "details": row.details,
                "requested_by": {"user_id": row.requested_by, "name": await name(row.requested_by)},
                "assignee": {"user_id": row.assignee_user_id, "name": await name(row.assignee_user_id)},
                "decided_by": row.decided_by and {"user_id": row.decided_by, "name": await name(row.decided_by)},
                "created_at": row.created_at, "decided_at": row.decided_at, "due_at": row.due_at}

    async def _subject_view(self, row: ApprovalRequest) -> dict:
        """What the person needs to decide, at the time they look."""
        if row.kind == "patch_review":
            p = await self.patches.get_patch(row.subject_id)
            return {"patch_id": p.id, "status": p.status, "reason": p.reason, "ops": p.ops,
                    "author": {"kind": p.author_kind, "id": p.author_id, "name": await self._name(p.author_id)},
                    "changed_paths": p.changed_paths, "base_version": p.base_version}
        if row.kind == "story_signoff":
            from services.ideas.service import IdeasService
            stories = await IdeasService(self.s, self.llm, clock=self.clock,
                                         correlation_id=self.correlation_id).stories(row.idea_id)
            current = (await self.patches.get_process(row.process_id)).current_version
            return {"ir_version": row.details.get("ir_version"), "current_version": current, "stories": stories}
        if row.kind == "suggestion":
            from services.improve.db import SuggestionRow
            s = await self.s.get(SuggestionRow, (row.subject_id, row.idea_id))
            return {"suggestion": s.as_suggestion() if s else None}
        from services.interviewer.db import Answer, Question
        q = await self.s.get(Question, row.subject_id)
        answer = (await self.s.execute(select(Answer).where(Answer.question_id == row.subject_id)
                                       .order_by(Answer.answered_at.desc()))).scalars().first()
        return {"question_id": row.subject_id, "text": q.text if q else row.title,
                "context": q.context_snippet if q else row.summary, "status": q.status if q else None,
                "answer": answer and {"text": answer.text, "answered_by": answer.answered_by,
                                      "answered_at": answer.answered_at}}

    # ------------------------------------------------------------------ helpers
    def _link(self, row: ApprovalRequest) -> str:
        return f"{self.web}/approvals/{row.id}"

    async def _name(self, user_id: str | None) -> str:
        if not user_id:
            return ""
        user = await self.s.get(User, user_id)
        return user.name if user else user_id

    async def _idea_title(self, idea_id: str | None) -> str:
        if not idea_id:
            return ""
        idea = await self.s.get(Idea, idea_id)
        return idea.title if idea else ""
