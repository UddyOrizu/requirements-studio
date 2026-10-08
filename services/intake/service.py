"""M0 intake: the conversation from an idea to ready stories (docs/modules/M0).

The service runs inside the caller's transaction and never commits (like M3). It decides what to ask with pure
functions (coverage, selection), asks the LLM only to interpret answers and phrase questions (S1, prompts/intake_*),
and changes the IR only through the Patch Service.
"""
import copy
import re
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import jsonpatch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from confidence_dor import DEFAULT_AUTHORITY_WEIGHTS, closure_hash, evaluate_dor
from gap_rules import fingerprint
from ir_core import Issue, PatchRejected
from ir_core.graph import live
from ir_core.ids import ELEMENT_COLLECTIONS, PREFIX_TO_COLLECTION
from ir_core.llm_models import DraftedACs, IntakeInterpretation, IntakeQuestion, Playback
from services.common.db import utcnow
from services.common.events import EventEnvelope
from services.common.outbox import enqueue_event
from services.common.uuid7 import uuid7
from services.gaps.db import GapRow
from services.gaps.store import stored_gaps, sync_gaps
from services.ideas.db import Idea
from services.identity_audit.audit import write_audit
from services.interviewer.db import Question, Sme
from services.ir_store.db import IrPatch, IrVersion
from services.ir_store.service import Actor, Conflict, NotFound, PatchService, empty_ir, iso, to_be_id_for
from services.llm_gateway import LLMGateway
from story_renderer import derive_stories

from .coverage import SLOT_KEY, coverage
from .db import IntakeSession, IntakeTurn, Signoff
from .selection import SessionState, Target, next_target

# Appended to every question's suggested answers (M0 design rule 3).
STANDARD_OPTIONS = ["Other…", "Not sure — ask someone", "Skip for now"]
# What the interpreter may write: every IR section except the derived/managed ones (M3 enforces those too).
ALLOWED_PATHS = sorted(f"/{c}" for c in [*ELEMENT_COLLECTIONS, "sources"]) + ["/scope"]
ID_CONVENTIONS = {"pattern": "<prefix>_<snake_case>", "prefixes": PREFIX_TO_COLLECTION,
                  "intake_source": "src_intake_<session id>", "inferred_source": "src_inferred"}
# Where an "ask someone" gap points when the requester could not answer a slot.
SLOT_SECTION = {"C01": "/goals", "C02": "/goals", "C03": "/personas", "C04": "/nodes", "C05": "/nodes",
                "C06": "/nodes", "C07": "/actors", "C08": "/decision_rules", "C09": "/exceptions",
                "C10": "/entities", "C11": "/actors", "C12": "/nfrs", "C13": "/slas", "C14": "/nfrs",
                "C15": "/scope", "C16": "/nodes", "C17": "/nodes"}
QUESTION_DUE = timedelta(days=2)
INTAKE_AGENT = Actor("agent", "agent:intake")


class InterpretationRejected(PatchRejected):
    """The interpreter's ops break a rule (verbatim excerpts); nothing is recorded and the answer can be retried."""


@dataclass
class NextQuestion:
    turn: str | None
    target: dict
    text: str | None = None
    why: str | None = None
    answer_type: str | None = None
    suggested_answers: list[str] = field(default_factory=list)


@dataclass
class TurnResult:
    session_id: str
    phase: str
    turn: str | None
    captured: list[str]
    assumptions: list[str]
    patch_id: str | None
    coverage: dict
    next_question: NextQuestion | None  # None while waiting (e.g. on M11 in Improve) or when done


def _norm(text: str | None) -> str:
    return re.sub(r"[\s.!]+$", "", (text or "").strip().lower())


def _slug(text: str, limit: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:limit].strip("_") or "idea"


def ir_view(ir: dict) -> dict:
    """The IR as the LLM sees it: no derived stories and no version/clock fields (so cassettes stay stable)."""
    view = {k: v for k, v in ir.items() if k != "stories"}
    view["process"] = {k: v for k, v in ir["process"].items() if k not in ("version", "updated_at")}
    return view


def provenance_refs(value: Any):
    """Every provenance ref inside an op value (nested element values or a ref added directly)."""
    if isinstance(value, dict):
        if "source_id" in value and "locator" in value:
            yield value
        for v in value.values():
            yield from provenance_refs(v)
    elif isinstance(value, list):
        for v in value:
            yield from provenance_refs(v)


AS_IS_SUFFIX, TO_BE_SUFFIX = ", as done today.", ", improved with AI agents where they help."


def to_be_description(as_is_description: str | None) -> str | None:
    """'…, as done today.' → '…, improved with AI agents where they help.'; anything else is kept."""
    if as_is_description and as_is_description.endswith(AS_IS_SUFFIX):
        return as_is_description.removesuffix(AS_IS_SUFFIX) + TO_BE_SUFFIX
    return as_is_description


def confirm_all_ops(ir: dict, user_id: str) -> list[dict]:
    """Playback "Yes": every proposed element becomes confirmed by the requester (M0 Playback)."""
    ops = []
    for coll in ELEMENT_COLLECTIONS:
        for eid, x in live(ir, coll).items():
            if x["meta"]["status"] == "proposed":
                ops += [{"op": "add", "path": f"/{coll}/{eid}/meta/confirmed_by", "value": user_id},
                        {"op": "replace", "path": f"/{coll}/{eid}/meta/status", "value": "confirmed"}]
    return ops


def drafted_ac_ops(ir: dict, drafted: DraftedACs) -> list[dict]:
    """AC drafting output → ops. Everything drafted is an assumption (src_inferred), confirmed in Validate."""
    inferred = {"source_id": "src_inferred", "locator": {"kind": "none", "value": ""}, "stance": "supports",
                "extraction_certainty": 0.8}
    ops = []
    for ac in drafted.criteria:
        if ac.ac_id in ir["acceptance_criteria"]:
            continue
        ops.append({"op": "add", "path": f"/acceptance_criteria/{ac.ac_id}", "value": {
            "title": ac.title, "kind": ac.kind, "applies_to": ac.applies_to, "given": ac.given, "when": ac.when,
            "then": ac.then, "meta": {"status": "proposed", "confidence": 0.0, "provenance": [inferred]}}})
    for step in drafted.outcomes:
        node = ir["nodes"].get(step.node_id)
        if node is None:
            continue
        goals = [g for g in step.goal_ids if g in ir["goals"]]
        if goals:
            ops.append({"op": "add", "path": f"/nodes/{step.node_id}/goal_ids", "value": goals})
        ops.append({"op": "add", "path": f"/nodes/{step.node_id}/outcome", "value": step.outcome})
        ops.append({"op": "add", "path": f"/nodes/{step.node_id}/meta/provenance/-", "value": inferred})
    return ops


class IntakeService:
    def __init__(self, session: AsyncSession, llm: LLMGateway, *, clock=utcnow, correlation_id: str | None = None):
        self.s, self.llm, self.clock = session, llm, clock
        self.patches = PatchService(session, clock=clock, correlation_id=correlation_id)
        self.correlation_id = self.patches.correlation_id

    # ================================================================== start
    async def start(self, *, idea_text: str, has_process_today: str, requester_id: str, requester_name: str,
                    requester_role: str | None = None, title: str | None = None, description: str | None = None,
                    domain: str | None = None, idea_id: str | None = None, session_id: str | None = None,
                    source_title: str | None = None) -> TurnResult:
        """New idea: idea + process (IR v0 with the intake source) + session; runs turn 0; returns the first question.

        has_process_today: "yes" → as-is mode; "no" or "not_sure" → idea mode (the to-be is captured directly).
        """
        mode = "as_is" if has_process_today == "yes" else "idea"
        variant = "as_is" if mode == "as_is" else "to_be"
        title = title or idea_text.split(".")[0][:80]
        slug = _slug(idea_id.removeprefix("idea_") if idea_id else title)
        idea_id = idea_id or f"idea_{slug}"
        session_id = session_id or f"is_{slug}"
        process_id = f"proc_{slug}_{variant}"
        now = self.clock()
        if await self.s.get(Idea, idea_id) or await self.s.get(IntakeSession, session_id):
            raise Conflict("/problems/idea-exists", f"{idea_id} already exists")

        idea = Idea(id=idea_id, title=title, summary=idea_text, owner_user_id=requester_id, status="discovering",
                    has_as_is=mode == "as_is", session_id=session_id, tags=[], stats={})
        self.s.add(idea)
        await self.s.flush()
        source_id = f"src_intake_{session_id}"
        header = {"id": process_id, "name": title, "owner_user_id": requester_id, "status": "draft", "version": 0,
                  "updated_at": iso(now), "variant": variant, "idea_id": idea_id}
        if description:
            header["description"] = description
        if domain:
            header["domain"] = domain
        v0 = empty_ir(header)
        v0["sources"][source_id] = {
            "title": source_title or f"Intake session with {requester_name}, {now.strftime('%-d %b %Y')}",
            "kind": "intake", "authority_weight": DEFAULT_AUTHORITY_WEIGHTS["intake"],
            "uri": f"rs://intake-sessions/{session_id}", "ingested_at": iso(now)}
        await self.patches.import_process(v0, actor=Actor("user", requester_id))
        if mode == "as_is":
            idea.as_is_process_id = process_id
        else:
            idea.to_be_process_id = process_id

        sess = IntakeSession(id=session_id, mode=mode, idea_id=idea_id, process_id=process_id,
                             requester_user_id=requester_id, phase="discover", status="active", coverage={},
                             parked=[], started_at=now, source_id=source_id,
                             state={"requester_name": requester_name, "requester_role": requester_role,
                                    "confirmed_playbacks": [], "turns": 0})
        self.s.add(sess)
        await self.s.flush()
        turn0 = await self._new_entry(sess, "turn", target=Target("idea", "idea").as_dict(), turn="T0")
        await write_audit(self.s, actor_kind="user", actor_id=requester_id, action="intake.started", target=sess.id,
                          process_id=process_id, after={"mode": mode, "idea_id": idea_id})
        return await self._answer(sess, turn0, text=idea_text, special=None, ask_sme_id=None)

    async def current(self, session_id: str) -> TurnResult:
        """Where the session stands: phase, coverage and the open question (if any)."""
        sess = await self._session(session_id)
        pending = await self._pending_turn(sess)
        nq = self._as_question(pending) if pending else (
            NextQuestion(None, sess.current_target) if (sess.current_target or {}).get("kind") == "signoff" else None)
        return TurnResult(sess.id, sess.phase, None, [], [], None, sess.coverage, nq)

    # ================================================================== answers
    async def answer(self, session_id: str, *, text: str | None = None, special: str | None = None,
                     ask_sme_id: str | None = None) -> TurnResult:
        sess = await self._session(session_id, lock=True)
        pending = await self._pending_turn(sess)
        if pending is None:
            raise Conflict("/problems/no-open-question", "there is no open question in this session",
                           phase=sess.phase)
        if not text and special is None:
            raise PatchRejected([Issue("envelope", "/text", "an answer needs text, a choice or a special option")])
        return await self._answer(sess, pending, text=text, special=special, ask_sme_id=ask_sme_id)

    async def _answer(self, sess: IntakeSession, turn: IntakeTurn, *, text: str | None, special: str | None,
                      ask_sme_id: str | None) -> TurnResult:
        target = Target(**turn.target)
        state = self._state(sess)
        ir = await self.patches.get_ir(sess.process_id)
        captured: list[str] = []
        assumptions: list[str] = []
        patch_id = None
        follow_up = None
        requester = Actor("user", sess.requester_user_id)

        if target.kind == "playback_confirm" and special is None and self._confirms(turn, text):
            ops = confirm_all_ops(ir, sess.requester_user_id)
            if ops:
                patch_id = await self._apply(sess, ops, f"{turn.turn}: playback confirmed", requester)
            n = len(ops) // 2
            captured.append(f"As-is confirmed ({n} elements)" if target.id == "as_is"
                            else f"Confirmed {n} elements, including all assumptions")
            state["confirmed_playbacks"] = sorted({*state["confirmed_playbacks"], target.id})
        elif special == "skip":
            self._park(sess, target)
            captured.append("Skipped for now")
        else:
            if text:
                result = await self._interpret(sess, turn, ir, text)
                captured += result.captured
                assumptions += result.assumptions
                if result.ops:
                    self._check_excerpts(sess, await self._answers_by_turn(sess, turn, text), result.ops)
                    ops = [op.model_dump(by_alias=True, exclude_unset=True) for op in result.ops]
                    patch_id = await self._apply(sess, ops, f"{turn.turn}: {_norm(text)[:120]}", requester)
                follow_up = result.follow_up_question if special is None else None
            if special == "not_sure_ask":
                captured.append(await self._ask_someone(sess, turn, text, ask_sme_id))
                self._park(sess, target)

        state["follow_up_of"] = turn.turn if follow_up else None
        state["follow_up_question"] = follow_up
        sess.state = {**state}
        ir = await self.patches.get_ir(sess.process_id)
        if sess.phase in ("deepen", "validate"):
            await sync_gaps(self.s, ir, patch_id=patch_id)
        cov = coverage(ir, sess.parked)
        sess.coverage = cov
        turn.answer_text, turn.special, turn.ask_sme_id, turn.patch_id = text, special, ask_sme_id, patch_id
        turn.captured, turn.assumptions, turn.follow_up_question = captured, assumptions, follow_up
        turn.coverage_after, turn.at = cov, self.clock()
        await self.s.flush()
        await enqueue_event(self.s, self._event("intake.turn_completed", sess, {
            "session_id": sess.id, "n": turn.n, "patch_id": patch_id, "coverage": cov["percent"]}))
        next_question = await self._advance(sess)
        return TurnResult(sess.id, sess.phase, turn.turn, captured, assumptions, patch_id, sess.coverage,
                          next_question)

    def _confirms(self, turn: IntakeTurn, text: str | None) -> bool:
        """The first suggested answer of a playback question is the confirmation ("That's right", "Confirm all")."""
        options = (turn.question or {}).get("suggested_answers") or []
        return bool(options) and _norm(text) == _norm(options[0])

    async def _interpret(self, sess: IntakeSession, turn: IntakeTurn, ir: dict, text: str) -> IntakeInterpretation:
        result, _ = await self.llm.complete_json("intake_interpret", {
            "target": await self._target_context(sess, Target(**turn.target)),
            "answer": text,
            "turn_id": turn.turn,
            "source_id": sess.source_id,
            "ir_view": ir_view(ir),
            "allowed_paths": ALLOWED_PATHS,
            "id_conventions": ID_CONVENTIONS,
        }, IntakeInterpretation, correlation_id=self.correlation_id, process_id=sess.process_id)
        return result

    def _check_excerpts(self, sess: IntakeSession, answers: dict[str, str], ops) -> None:
        """M0 §3: every intake provenance excerpt is a verbatim substring of the answer of the turn it cites."""
        problems = []
        for i, op in enumerate(ops):
            for ref in provenance_refs(op.value):
                if ref["source_id"] != sess.source_id:
                    continue
                cited = ref["locator"].get("value")
                if ref.get("excerpt") is None or ref["excerpt"] not in answers.get(cited, ""):
                    problems.append(Issue("envelope", f"/ops/{i}",
                                          f"excerpt {ref.get('excerpt')!r} is not verbatim in the answer to {cited}"))
        if problems:
            raise InterpretationRejected(problems)

    async def _answers_by_turn(self, sess: IntakeSession, current: IntakeTurn, text: str) -> dict[str, str]:
        rows = await self._entries(sess)
        answers = {r.turn: r.answer_text for r in rows if r.turn and r.answer_text}
        answers[current.turn] = text
        return answers

    async def _apply(self, sess: IntakeSession, ops: list[dict], reason: str, author: Actor) -> str:
        """Requester answers are user patches with auto_apply (M0 §3). Returns the patch id."""
        proc = await self.patches.get_process(sess.process_id)
        patch = {"patch_id": f"patch_{sess.id}_{uuid7().hex[:12]}", "process_id": sess.process_id,
                 "base_version": proc.current_version, "ops": ops, "author": {"kind": author.kind, "id": author.id},
                 "reason": reason[:500], "auto_apply": True, "status": "proposed",
                 "evidence": {"source_ids": [sess.source_id]}}
        result = await self.patches.submit(patch, actor=author)
        if result.status == "proposed":  # an agent patch (AC drafting): drafted items are assumptions; apply them
            result = await self.patches.accept(result.patch_id, reviewer=Actor("system", "intake"))
        if result.status != "applied":
            raise Conflict("/problems/patch-conflict", "the change conflicts with newer changes",
                           conflicting_paths=result.conflicting_paths)
        return result.patch_id

    # ================================================================== ask someone (M6)
    async def _ask_someone(self, sess: IntakeSession, turn: IntakeTurn, text: str | None,
                           sme_id: str | None) -> str:
        """Create the SME question and the intake gap behind it; the target is parked by the caller."""
        if not sme_id:
            raise PatchRejected([Issue("envelope", "/ask_sme_id",
                                       "name the person to ask (automatic SME routing arrives with M6)")])
        sme = await self.s.get(Sme, sme_id)
        if sme is None:
            raise PatchRejected([Issue("envelope", "/ask_sme_id", f"unknown SME {sme_id}")])
        ir = await self.patches.get_ir(sess.process_id)
        target = Target(**turn.target)
        question = turn.question or {}
        options = [o for o in question.get("suggested_answers", []) if o not in STANDARD_OPTIONS]
        answer_type = {"multi_choice": "choice"}.get(question.get("answer_type"), question.get("answer_type"))
        answer_type = answer_type or "free_text"

        if target.kind == "gap" and (gap := await self.s.get(GapRow, target.id)):
            gap.status = "asked"
        else:
            refs = [SLOT_SECTION.get(target.id, "/nodes")]
            gap_type = "integration_capability_unknown" if target.id == "C11" else "unclear_business_rule"
            gap = GapRow(id=f"gap_intake_{sess.id.removeprefix('is_')}_{turn.turn.lower()}"[:64],
                         process_id=sess.process_id, fingerprint=fingerprint(gap_type, refs), type=gap_type,
                         severity="major", detector="intake", target_refs=refs,
                         title=question.get("text", "Question for an expert")[:200],
                         why_it_matters=question.get("why", ""),
                         question={"text": question.get("text", ""), "answer_type": answer_type,
                                   "suggested_answers": options},
                         routing={"topic_tags": [SLOT_KEY.get(target.id, target.kind)],
                                  "candidate_actor_ids": list(sme.actor_ids)},
                         priority=4, status="asked", ir_version_detected=ir["process"]["version"])
            self.s.add(gap)
        now = self.clock()
        q = Question(id=f"q_{uuid7().hex}", process_id=sess.process_id, origin="intake_ask_someone",
                     asked_by=sess.requester_user_id, gap_ids=[gap.id], sme_id=sme.id,
                     channel="email" if "email" in sme.channels else "in_app",  # email or portal (no Teams yet)
                     text=question.get("text", "")[:400], context_snippet=(text or "")[:600],
                     answer_type=answer_type, suggested_answers=options, status="sent", sent_at=now,
                     due_at=now + QUESTION_DUE)
        self.s.add(q)
        await self.s.flush()
        turn.payload = {**turn.payload, "question_id": q.id, "parked": [gap.id]}
        await enqueue_event(self.s, self._event("question.sent", sess, {"question_id": q.id, "sme_id": sme.id}))
        await write_audit(self.s, actor_kind="user", actor_id=sess.requester_user_id, action="question.sent",
                          target=q.id, process_id=sess.process_id, after={"sme_id": sme.id, "gap_id": gap.id})
        role = f" ({sme.role_title})" if sme.role_title else ""
        return f"Asked {sme.name}{role}: {q.text}"

    async def record_sme_answer(self, session_id: str, *, question_id: str, patch_id: str, answered_by: str,
                                answer_text: str, captured: list[str]) -> None:
        """M6 hook (question.answered): show the SME's answer as a captured card. The patch is accepted through M3."""
        sess = await self._session(session_id, lock=True)
        question = await self.s.get(Question, question_id)
        if question is None:
            raise NotFound(f"question {question_id} not found")
        question.status = "answered"
        await self._new_entry(sess, "sme_answer", patch_id=patch_id, captured=captured, answer_text=answer_text,
                              payload={"question_id": question_id, "author": "agent:interviewer",
                                       "answer_by": answered_by})

    # ================================================================== undo, jump, sign-off
    async def record_suggestion_decision(self, sess: IntakeSession, suggestion_id: str, decision: str, answer: str,
                                         user_id: str, patch_id: str | None, captured: list[str],
                                         ops: list[dict] | None) -> None:
        """M11 hook: each accept/reject is a timeline entry (accepted ones carry their patch)."""
        await self._new_entry(sess, "suggestion_decision", target={"kind": "suggestion", "id": suggestion_id},
                              answer_text=answer, patch_id=patch_id, captured=captured,
                              payload={"suggestion_id": suggestion_id, "decision": decision, "answer_by": user_id})

    async def undo(self, session_id: str, n: int) -> TurnResult:
        """Inverse patch of entry n (M0 §3). 409 when later changes touched the same paths."""
        sess = await self._session(session_id, lock=True)
        entry = (await self.s.execute(select(IntakeTurn).where(IntakeTurn.session_id == sess.id,
                                                               IntakeTurn.n == n))).scalar_one_or_none()
        if entry is None or entry.patch_id is None:
            raise NotFound(f"entry {n} of {session_id} has no change to undo")
        if entry.undone_by_patch_id:
            raise Conflict("/problems/already-undone", f"entry {n} was already undone")
        patch = await self.s.get(IrPatch, entry.patch_id)
        before = await self.s.get(IrVersion, (patch.process_id, patch.applied_version - 1))
        after = await self.s.get(IrVersion, (patch.process_id, patch.applied_version))
        ops = [op for op in jsonpatch.make_patch(ir_view(after.snapshot), ir_view(before.snapshot)).patch]
        undo = {"patch_id": f"patch_{sess.id}_undo_{uuid7().hex[:12]}", "process_id": patch.process_id,
                "base_version": patch.applied_version, "ops": ops,
                "author": {"kind": "user", "id": sess.requester_user_id},
                "reason": f"Undo {entry.turn or entry.kind} (entry {n})", "auto_apply": True, "status": "proposed"}
        result = await self.patches.submit(undo, actor=Actor("user", sess.requester_user_id))
        if result.status != "applied":
            raise Conflict("/problems/undo-conflict", "later changes touch the same elements; undo those first",
                           conflicting_paths=result.conflicting_paths)
        entry.undone_by_patch_id = result.patch_id
        state = self._state(sess)
        if state.get("follow_up_of") == entry.turn:
            state["follow_up_of"] = state["follow_up_question"] = None
            sess.state = state
        ir = await self.patches.get_ir(sess.process_id)
        sess.coverage = coverage(ir, sess.parked)
        await self.s.flush()
        pending = await self._pending_turn(sess)
        return TurnResult(sess.id, sess.phase, entry.turn, [f"Undid {entry.turn or entry.kind}"], [],
                          result.patch_id, sess.coverage, self._as_question(pending) if pending else None)

    async def jump(self, session_id: str, phase: str) -> TurnResult:
        """'Show me the stories now': go to Validate with whatever exists (M0 design rule 7)."""
        if phase != "validate":
            raise PatchRejected([Issue("envelope", "/phase", "only a jump to validate is allowed")])
        sess = await self._session(session_id, lock=True)
        if sess.phase in ("improve", "validate", "done"):
            raise Conflict("/problems/cannot-jump", f"cannot jump to validate from {sess.phase}")
        await self._drop_pending(sess)
        await self._enter_phase(sess, "validate")
        return TurnResult(sess.id, sess.phase, None, [], [], None, sess.coverage, await self._advance(sess))

    async def complete_improve(self, session_id: str) -> TurnResult:
        """M11 hook: every suggestion decided → Deepen on the to-be."""
        sess = await self._session(session_id, lock=True)
        if sess.phase != "improve":
            raise Conflict("/problems/not-improving", f"session is in {sess.phase}")
        await self._enter_phase(sess, "deepen")
        return TurnResult(sess.id, sess.phase, None, [], [], None, sess.coverage, await self._advance(sess))

    async def sign_off(self, session_id: str, *, user_id: str) -> TurnResult:
        """The requester signs off every story; allowed once only DOR-11 (sign-off itself) is failing."""
        sess = await self._session(session_id, lock=True)
        if sess.phase != "validate" or Target(**(sess.current_target or {"kind": "x", "id": ""})).kind != "signoff":
            raise Conflict("/problems/not-ready-for-signoff", "sign-off comes after the final playback in Validate")
        ir = await self.patches.get_ir(sess.process_id)
        gaps = [r.as_gap() for r in await stored_gaps(self.s, sess.process_id)]
        stories = derive_stories(ir, gaps)
        rows = evaluate_dor(ir, stories, gaps, signoffs=set(stories))
        blocked = {r["story_id"]: r["failed_checks"] for r in rows if r["status"] != "ready"}
        if blocked:
            raise Conflict("/problems/stories-not-ready", "some stories are not ready", failing=blocked)
        now = self.clock()
        for sid, story in stories.items():
            self.s.add(Signoff(process_id=sess.process_id, story_id=sid, ir_version=ir["process"]["version"],
                               closure_hash=closure_hash(ir, story), signed_by=user_id, signed_at=now))
        name = self._state(sess).get("requester_name") or user_id
        variant = ir["process"]["variant"].replace("_", "-")
        await self._new_entry(sess, "signoff", target=Target("signoff", "all").as_dict(),
                              captured=[f"{name} signed off {len(stories)} stories at {variant} version "
                                        f"{ir['process']['version']}"],
                              payload={"story_ids": sorted(stories)})
        await write_audit(self.s, actor_kind="user", actor_id=user_id, action="stories.signed_off",
                          target=sess.process_id, process_id=sess.process_id,
                          after={"story_ids": sorted(stories), "ir_version": ir["process"]["version"]})
        await self._enter_phase(sess, "done")
        return TurnResult(sess.id, sess.phase, None, [], [], None, sess.coverage, None)

    # ================================================================== advancing
    async def _advance(self, sess: IntakeSession) -> NextQuestion | None:
        """Pick the next target (pure), act on phase changes, phrase the question and open the next turn."""
        for _ in range(8):  # at most one pass per phase
            ir = await self.patches.get_ir(sess.process_id)
            gaps = ([r.as_gap() for r in await stored_gaps(self.s, sess.process_id)]
                    if sess.phase in ("deepen", "validate") else [])
            target = next_target(self._selection_state(sess), ir, gaps)
            sess.current_target = target.as_dict()
            if target.kind == "phase":
                if target.id == sess.phase:
                    return None  # Improve waits for M11
                await self._enter_phase(sess, target.id)
                if sess.phase == "done":
                    return None
                continue
            if target.kind == "signoff":
                return NextQuestion(None, target.as_dict())
            if target.kind == "playback_confirm":
                await self._playback(sess, ir)
            question = await self._phrase(sess, target, ir, gaps)
            state = self._state(sess)
            state["turns"] = state.get("turns", 0) + 1
            sess.state = state
            turn = await self._new_entry(sess, "turn", target=target.as_dict(), turn=f"T{state['turns']}",
                                         question=question)
            return self._as_question(turn)
        raise RuntimeError("intake did not settle on a next question")

    async def _phrase(self, sess: IntakeSession, target: Target, ir: dict, gaps: list[dict]) -> dict:
        state = self._state(sess)
        recent = [{"question": (r.question or {}).get("text"), "answer": r.answer_text}
                  for r in await self._entries(sess) if r.kind == "turn" and r.answer_text][-3:]
        result, _ = await self.llm.complete_json("intake_phrase", {
            "target": await self._target_context(sess, target),
            "slot_key": SLOT_KEY.get(target.id) if target.kind == "slot" else None,
            "gap": next((self._gap_context(g) for g in gaps if g["gap_id"] == target.id), None),
            "ir_summary": self._summary(ir),
            "recent_turns": recent,
            "requester_role": state.get("requester_role") or "requester",
            "mode": sess.mode,
        }, IntakeQuestion, correlation_id=self.correlation_id, process_id=sess.process_id)
        return {"text": result.text, "why": result.why, "answer_type": result.answer_type,
                "suggested_answers": [*result.suggested_answers, *STANDARD_OPTIONS]}

    async def _playback(self, sess: IntakeSession, ir: dict) -> None:
        result, _ = await self.llm.complete_json("intake_playback", {"ir_view": ir_view(ir)}, Playback,
                                                 correlation_id=self.correlation_id, process_id=sess.process_id)
        await self._new_entry(sess, "playback", payload={"playback_text": result.summary})

    async def _enter_phase(self, sess: IntakeSession, to: str) -> None:
        frm = sess.phase
        sess.phase = to
        await self._new_entry(sess, "phase_change", payload={"from_phase": frm, "to_phase": to})
        await enqueue_event(self.s, self._event("intake.phase_changed", sess,
                                                {"session_id": sess.id, "from": frm, "to": to}))
        idea = await self.s.get(Idea, sess.idea_id) if sess.idea_id else None
        if to == "improve":
            as_is = await self.patches.get_ir(sess.process_id)
            fork = await self.patches.fork(sess.process_id, actor=Actor("user", sess.requester_user_id),
                                           to_process_id=to_be_id_for(sess.process_id),
                                           description=to_be_description(as_is["process"].get("description")))
            sess.process_id = fork.to_be_process_id
            await self._new_entry(sess, "fork", payload={"fork": fork.fork}, process_variant="to_be")
            if idea:
                idea.status = "improving"
                idea.to_be_process_id = fork.to_be_process_id
            await self.s.flush()
            from services.improve.service import ImproveService  # M11 decides; it calls back into M0
            generated = await ImproveService(self.s, self.llm, clock=self.clock,
                                             correlation_id=self.correlation_id).generate(
                sess.idea_id, requester_name=self._state(sess).get("requester_name"))
            await self._new_entry(sess, "suggestions", patch_id=generated.patch_id, captured=generated.captured,
                                  payload={"suggestion_ids": [s["suggestion_id"] for s in generated.suggestions],
                                           "not_suggested": generated.not_suggested})
            if not generated.suggestions:
                await self._enter_phase(sess, "deepen")
                return
        elif to == "deepen":
            await self._draft_acs(sess)
            await sync_gaps(self.s, await self.patches.get_ir(sess.process_id), patch_id=None)
        elif to == "validate":
            await sync_gaps(self.s, await self.patches.get_ir(sess.process_id), patch_id=None)
            if idea:
                idea.status = "refining"
        elif to == "done":
            sess.status, sess.completed_at = "completed", self.clock()
            if idea:
                idea.status = "ready"
        await self.s.flush()

    async def _draft_acs(self, sess: IntakeSession) -> None:
        """Entering Deepen: draft ACs, outcomes and goal links for steps without ACs (assumptions; M0 §3)."""
        ir = await self.patches.get_ir(sess.process_id)
        covered = {t for a in live(ir, "acceptance_criteria").values() for t in a["applies_to"]}
        needing = [k for k, n in live(ir, "nodes").items() if n["type"] in ("task", "decision") and k not in covered]
        if not needing:
            return
        stories = derive_stories(ir, [])
        closures = [{"story_id": sid, "node_ids": s["node_ids"], "title": s["title"],
                     "nodes": {n: ir["nodes"][n] for n in s["node_ids"]},
                     "exceptions": [e["ref"] for e in s["edge_cases"] if e["ref"].startswith("exc_")]}
                    for sid, s in stories.items() if set(s["node_ids"]) & set(needing)]
        drafted, _ = await self.llm.complete_json("intake_draft_acs", {
            "story_closures": closures,
            "existing_acs": {k: {"title": a["title"], "applies_to": a["applies_to"]}
                             for k, a in live(ir, "acceptance_criteria").items()},
        }, DraftedACs, correlation_id=self.correlation_id, process_id=sess.process_id)
        ops = drafted_ac_ops(ir, drafted)
        if not ops:
            return
        patch_id = await self._apply(sess, ops, "Drafted acceptance criteria, outcomes and goal links", INTAKE_AGENT)
        n_acs = sum(op["path"].startswith("/acceptance_criteria/") for op in ops)
        await self._new_entry(sess, "system_patch", patch_id=patch_id,
                              captured=[f"Drafted {n_acs} acceptance criteria (incl. edge cases) for the steps",
                                        "Drafted an outcome for each step and linked steps to goals"],
                              assumptions=["All drafted acceptance criteria, outcomes and goal links are my "
                                           "assumptions; you'll confirm them in Validate"],
                              payload={"author": INTAKE_AGENT.id})

    # ================================================================== helpers
    async def _target_context(self, sess: IntakeSession, target: Target) -> dict:
        context = target.as_dict()
        if target.kind == "slot":
            context["slot_key"] = SLOT_KEY[target.id]
        elif target.kind == "follow_up":
            context["question"] = self._state(sess).get("follow_up_question")
        elif target.kind == "gap" and (gap := await self.s.get(GapRow, target.id)):
            context["gap"] = self._gap_context(gap.as_gap())
        return context

    @staticmethod
    def _gap_context(g: dict) -> dict:
        return {"type": g["type"], "severity": g["severity"], "title": g["title"], "target_refs": g["target_refs"],
                "question": g["question"]["text"]}

    @staticmethod
    def _summary(ir: dict) -> dict:
        return {"process": ir["process"]["name"], "variant": ir["process"]["variant"],
                "steps": [n["name"] for n in live(ir, "nodes").values() if n["type"] == "task"],
                "actors": [a["name"] for a in live(ir, "actors").values()],
                "goals": [g["statement"] for g in live(ir, "goals").values()]}

    def _park(self, sess: IntakeSession, target: Target) -> None:
        if target.id not in sess.parked:
            sess.parked = [*sess.parked, target.id]

    def _state(self, sess: IntakeSession) -> dict:
        return {"confirmed_playbacks": [], "turns": 0, **copy.deepcopy(sess.state or {})}

    def _selection_state(self, sess: IntakeSession) -> SessionState:
        state = self._state(sess)
        return SessionState(mode=sess.mode, phase=sess.phase, parked=list(sess.parked),
                            follow_up_of=state.get("follow_up_of"), follow_up_question=state.get("follow_up_question"),
                            confirmed_playbacks=set(state["confirmed_playbacks"]))

    async def _session(self, session_id: str, *, lock: bool = False) -> IntakeSession:
        q = select(IntakeSession).where(IntakeSession.id == session_id)
        sess = (await self.s.execute(q.with_for_update() if lock else q)).scalar_one_or_none()
        if sess is None:
            raise NotFound(f"intake session {session_id} not found")
        return sess

    async def _entries(self, sess: IntakeSession) -> list[IntakeTurn]:
        q = select(IntakeTurn).where(IntakeTurn.session_id == sess.id).order_by(IntakeTurn.n)
        return list((await self.s.execute(q)).scalars())

    async def _pending_turn(self, sess: IntakeSession) -> IntakeTurn | None:
        rows = [r for r in await self._entries(sess) if r.kind == "turn"]
        last = rows[-1] if rows else None
        return last if last is not None and last.answer_text is None and last.special is None else None

    async def _drop_pending(self, sess: IntakeSession) -> None:
        if pending := await self._pending_turn(sess):
            await self.s.delete(pending)
            state = self._state(sess)
            state["turns"] = max(0, state.get("turns", 0) - 1)
            sess.state = state
            await self.s.flush()

    async def _new_entry(self, sess: IntakeSession, kind: str, *, target: dict | None = None,
                         turn: str | None = None, question: dict | None = None, patch_id: str | None = None,
                         captured: list[str] | None = None, assumptions: list[str] | None = None,
                         answer_text: str | None = None, payload: dict | None = None,
                         process_variant: str | None = None) -> IntakeTurn:
        rows = await self._entries(sess)
        variant = process_variant or ("as_is" if sess.process_id.endswith("_as_is") else "to_be")
        entry = IntakeTurn(session_id=sess.id, n=(rows[-1].n + 1) if rows else 0, kind=kind, turn=turn,
                           process_variant=variant, phase=sess.phase, target=target, question=question,
                           patch_id=patch_id, captured=captured, assumptions=assumptions, answer_text=answer_text,
                           at=self.clock(), payload=payload or {})
        self.s.add(entry)
        await self.s.flush()
        return entry

    @staticmethod
    def _as_question(turn: IntakeTurn) -> NextQuestion:
        q = turn.question or {}
        return NextQuestion(turn.turn, turn.target, q.get("text"), q.get("why"), q.get("answer_type"),
                            q.get("suggested_answers", []))

    def _event(self, type_: str, sess: IntakeSession, payload: dict) -> EventEnvelope:
        return EventEnvelope(type=type_, process_id=sess.process_id, correlation_id=self.correlation_id,
                             payload=payload)

    # ================================================================== export
    async def export(self, session_id: str) -> dict:
        """The session in schemas/intake-session.schema.json shape."""
        sess = await self._session(session_id)
        idea = await self.s.get(Idea, sess.idea_id) if sess.idea_id else None
        timeline = []
        for r in await self._entries(sess):
            e: dict[str, Any] = {"seq": r.n, "kind": r.kind, "phase": r.phase, "at": iso(r.at),
                                 "process": r.process_variant}
            if r.turn:
                e["turn"] = r.turn
            if r.target:
                e["target"] = r.target
            if r.question:
                e["question"] = r.question
            if r.answer_text is not None or r.special:
                answer = {"by": r.payload.get("answer_by", sess.requester_user_id)}
                if r.answer_text is not None:
                    answer["text"] = r.answer_text
                if r.special:
                    answer["special"] = r.special
                if r.ask_sme_id:
                    answer["ask_sme_id"] = r.ask_sme_id
                e["answer"] = answer
            for key in ("captured", "assumptions"):
                if getattr(r, key) is not None:
                    e[key] = getattr(r, key)
            if r.kind == "turn" and r.answer_text is not None:
                e["follow_up_question"] = r.follow_up_question
            if r.patch_id:
                e["patch_id"] = r.patch_id
                patch = await self.s.get(IrPatch, r.patch_id)
                if patch and patch.applied_version is not None:
                    e["ir_version_after"] = patch.applied_version
            if r.coverage_after:
                e["coverage_after"] = r.coverage_after
            for key in ("playback_text", "from_phase", "to_phase", "question_id", "parked", "fork", "story_ids",
                        "author", "suggestion_ids", "suggestion_id", "decision"):
                if key in r.payload:
                    e[key] = r.payload[key]
            timeline.append(e)
        return {"session_id": sess.id, "idea_id": sess.idea_id, "mode": sess.mode, "process_id": sess.process_id,
                "as_is_process_id": idea.as_is_process_id if idea else None,
                "to_be_process_id": (idea.to_be_process_id if idea else None) or sess.process_id,
                "requester_user_id": sess.requester_user_id, "source_id": sess.source_id,
                "idea_text": idea.summary if idea else "", "phase": sess.phase, "status": sess.status,
                "started_at": iso(sess.started_at), "timeline": timeline, "parked_questions": [],
                "final_coverage": (sess.coverage or {}).get("percent", 0)}

