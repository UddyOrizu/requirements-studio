"""M11 As-is analysis & AI improvement (docs/modules/M11).

Generate: heuristics find candidates → prompts/improve_suggest.md words them, picks evidence, proposes ops →
guardrails drop or correct what breaks a rule. Decide: accept applies the ops to the to-be as one patch; reject keeps
today's behaviour with the reason recorded; edit revises one suggestion through prompts/improve_edit.md.
Every decision is recorded on the intake timeline; when all are decided, M0 moves on to Deepen.
"""
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from confidence_dor import DEFAULT_AUTHORITY_WEIGHTS
from exporters import improvements_md
from improve import candidates, cases_per_month, check, complete_ops, protected_approvals
from ir_core import Issue, PatchRejected
from ir_core.ids import ELEMENT_COLLECTIONS
from ir_core.llm_models import SuggestedChange, SuggestionList
from services.common.db import utcnow
from services.common.uuid7 import uuid7
from services.ideas.db import Idea
from services.identity_audit.audit import write_audit
from services.ir_store.service import Actor, Conflict, NotFound, PatchService, iso
from services.llm_gateway import LLMGateway

from .db import SuggestionRow

LOW_CONFIDENCE_CAP = 0.5  # candidates the heuristics mark "low" (narrow approvals)
DECIDED = {"accepted", "rejected"}


@dataclass
class Generated:
    suggestions: list[dict]
    not_suggested: list[dict] = field(default_factory=list)
    captured: list[str] = field(default_factory=list)
    patch_id: str | None = None


class ImproveService:
    def __init__(self, session: AsyncSession, llm: LLMGateway, *, clock=utcnow, correlation_id: str | None = None):
        self.s, self.llm, self.clock = session, llm, clock
        self.patches = PatchService(session, clock=clock, correlation_id=correlation_id)

    # ------------------------------------------------------------------ context
    async def _idea(self, idea_id: str) -> Idea:
        idea = await self.s.get(Idea, idea_id)
        if idea is None:
            raise NotFound(f"idea {idea_id} not found")
        if not idea.as_is_process_id or not idea.to_be_process_id:
            raise Conflict("/problems/no-to-be", "suggestions need a confirmed, forked as-is (M11 fork)")
        return idea

    async def _intake(self, idea: Idea):
        from services.intake.db import IntakeSession  # M0 owns the session; imported lazily (M0 calls M11)
        return await self.s.get(IntakeSession, idea.session_id)

    async def _evidence_texts(self, idea: Idea, as_is: dict) -> tuple[dict[str, str], dict[str, list[str]], list[str]]:
        """(turn label → requester answer, source id → quotable texts, SME answers) for guardrail 3."""
        from services.intake.db import IntakeTurn
        rows = list((await self.s.execute(select(IntakeTurn).where(IntakeTurn.session_id == idea.session_id)
                                          .order_by(IntakeTurn.n))).scalars())
        turns = {r.turn: r.answer_text for r in rows if r.turn and r.answer_text}
        sme = [r.answer_text for r in rows if r.kind == "sme_answer" and r.answer_text]
        texts: dict[str, list[str]] = {}
        for coll in ELEMENT_COLLECTIONS:
            for x in as_is[coll].values():
                for p in x["meta"]["provenance"]:
                    if p.get("excerpt"):
                        texts.setdefault(p["source_id"], []).append(p["excerpt"])
        for sid, src in as_is["sources"].items():
            if src["kind"] == "interview_answer":
                texts.setdefault(sid, []).extend(sme)
        return turns, texts, sme

    # ------------------------------------------------------------------ generate
    async def generate(self, idea_id: str, *, requester_name: str | None = None) -> Generated:
        """Suggest improvements for every candidate step not already suggested ("Suggest more" keeps decisions)."""
        idea = await self._idea(idea_id)
        as_is = await self.patches.get_ir(idea.as_is_process_id)
        to_be = await self.patches.get_ir(idea.to_be_process_id)
        existing = {r.target_refs[0]: r for r in await self._rows(idea_id)}
        turns, texts, sme_answers = await self._evidence_texts(idea, as_is)
        protected = protected_approvals(as_is)
        cases = cases_per_month(as_is)
        cands = [c for c in candidates(as_is, sme_answers=sme_answers) if c.target_ref not in existing]
        not_suggested = [{"target": as_is["nodes"][c.target]["name"], "reason": f"out of scope: {protected[c.target]}"}
                         for c in cands if c.target in protected]
        cands = [c for c in cands if c.target not in protected]
        if not cands:
            return Generated([], not_suggested)

        sess = await self._intake(idea)
        source_id = f"src_improve_{sess.id}"
        patch_id = None
        if source_id not in to_be["sources"]:
            patch_id = await self._add_source(idea, to_be, source_id, requester_name or idea.owner_user_id)
            to_be = await self.patches.get_ir(idea.to_be_process_id)

        result, _ = await self.llm.complete_json("improve_suggest", {
            "as_is_view": _view(as_is),
            "candidates": [c.as_dict() for c in cands],
            "pain_points": {c.target: c.pain_points for c in cands if c.pain_points},
            "effort": {c.target: c.minutes_per_case for c in cands if c.minutes_per_case is not None},
            "sme_answers": sme_answers,
            "scope": as_is["scope"],
            "cases_per_month": cases,
            "id_conventions": {"suggestion_ids": "S01, S02, … in your order", "source": source_id},
        }, SuggestionList, correlation_id=self.patches.correlation_id, process_id=idea.to_be_process_id)

        by_target = {c.target_ref: c for c in cands}
        number = len(existing)
        kept: list[dict] = []
        not_suggested += [{"target": n.target, "reason": n.reason} for n in result.not_suggested]
        for proposal in result.suggestions:
            candidate = next((by_target[r] for r in proposal.target_refs if r in by_target), None)
            number += 1
            s = self._from_proposal(proposal, idea_id, f"S{number:02d}", candidate)
            verdict = check(s, to_be, protected=protected, cases=cases, turn_answers=turns, source_texts=texts,
                            qualitative=proposal.qualitative)
            if verdict.suggestion is None:
                not_suggested.append(verdict.not_suggested)
                number -= 1
                continue
            kept.append(verdict.suggestion)
            self.s.add(_row(verdict.suggestion, source="heuristic" if candidate else "llm"))
        for c in cands:
            if not any(c.target_ref in s["target_refs"] for s in kept) and not any(
                    n["target"] == as_is["nodes"][c.target]["name"] for n in not_suggested):
                not_suggested.append({"target": as_is["nodes"][c.target]["name"],
                                      "reason": "no proposal came back for this step; ask for more suggestions"})
        await self.s.flush()
        hours = sum(s["benefit"].get("hours_saved_per_month") or 0 for s in kept)
        captured = [f"{len(kept)} improvement suggestions, about {hours:g} analyst hours a month if all accepted"]
        captured += [f"Not suggested: {n['target']} ({n['reason']})" for n in not_suggested]
        await write_audit(self.s, actor_kind="agent", actor_id="agent:improve", action="suggestions.generated",
                          target=idea_id, process_id=idea.to_be_process_id,
                          after={"suggestion_ids": [s["suggestion_id"] for s in kept], "not_suggested": not_suggested})
        return Generated(kept, not_suggested, captured, patch_id)

    def _from_proposal(self, p: SuggestedChange, idea_id: str, sid: str, candidate) -> dict:
        confidence = p.confidence
        if candidate is not None and candidate.confidence_hint == "low":
            confidence = min(confidence, LOW_CONFIDENCE_CAP)
        s = {"suggestion_id": sid, "idea_id": idea_id, "kind": p.kind,
             "target_refs": p.target_refs or ([candidate.target_ref] if candidate else []),
             "title": p.title, "change_summary": p.change_summary, "rationale": p.rationale,
             "evidence": [{"source_id": e.source_id or "", "locator": e.locator, "excerpt": e.excerpt}
                          for e in p.evidence],
             "benefit": {}, "controls": p.controls, "risk": p.risk, "confidence": confidence, "status": "proposed",
             "decision": None, "ops": [op.model_dump(by_alias=True, exclude_unset=True) for op in p.ops]}
        return s

    async def _add_source(self, idea: Idea, to_be: dict, source_id: str, requester_name: str) -> str:
        now = self.clock()
        source = {"title": f"AI improvement suggestions accepted by {requester_name}, {now.strftime('%-d %b %Y')}",
                  "kind": "suggestion", "authority_weight": DEFAULT_AUTHORITY_WEIGHTS["suggestion"],
                  "uri": f"rs://ideas/{idea.id}/suggestions", "ingested_at": iso(now)}
        result = await self.patches.submit({
            "patch_id": f"patch_{idea.id}_improve_{uuid7().hex[:12]}", "process_id": idea.to_be_process_id,
            "base_version": to_be["process"]["version"], "author": {"kind": "agent", "id": "agent:improve"},
            "ops": [{"op": "add", "path": f"/sources/{source_id}", "value": source}], "reason": "Improvement source",
            "auto_apply": True, "status": "proposed"}, actor=Actor("agent", "agent:improve"))
        if result.status == "proposed":
            result = await self.patches.accept(result.patch_id, reviewer=Actor("system", "improve"))
        return result.patch_id

    # ------------------------------------------------------------------ decide
    async def list_suggestions(self, idea_id: str) -> list[dict]:
        return [r.as_suggestion() for r in await self._rows(idea_id)]

    async def _rows(self, idea_id: str) -> list[SuggestionRow]:
        q = select(SuggestionRow).where(SuggestionRow.idea_id == idea_id).order_by(SuggestionRow.id)
        return list((await self.s.execute(q)).scalars())

    async def _row(self, idea_id: str, sid: str, *, lock: bool = True) -> SuggestionRow:
        q = select(SuggestionRow).where(SuggestionRow.idea_id == idea_id, SuggestionRow.id == sid)
        row = (await self.s.execute(q.with_for_update() if lock else q)).scalar_one_or_none()
        if row is None:
            raise NotFound(f"suggestion {sid} of {idea_id} not found")
        if row.status in DECIDED:
            raise Conflict("/problems/suggestion-decided", f"{sid} is already {row.status}", status_now=row.status)
        return row

    async def accept(self, idea_id: str, sid: str, *, user_id: str) -> dict:
        """Apply the suggestion's ops to the to-be as one patch (author = requester); touched nodes get `change`."""
        idea = await self._idea(idea_id)
        row = await self._row(idea_id, sid)
        to_be = await self.patches.get_ir(idea.to_be_process_id)
        sess = await self._intake(idea)
        ops = complete_ops(row.as_suggestion(), to_be, source_id=f"src_improve_{sess.id}", requester_id=user_id)
        result = await self.patches.submit({
            "patch_id": f"patch_{idea.id}_{sid.lower()}_{uuid7().hex[:8]}", "process_id": idea.to_be_process_id,
            "base_version": to_be["process"]["version"], "ops": ops, "author": {"kind": "user", "id": user_id},
            "reason": f"Accepted {sid}: {row.title}", "auto_apply": True, "status": "proposed",
            "evidence": {"source_ids": [f"src_improve_{sess.id}"]}}, actor=Actor("user", user_id))
        if result.status != "applied":
            raise Conflict("/problems/patch-conflict", "the to-be changed in the same place; regenerate this one",
                           conflicting_paths=result.conflicting_paths)
        row.status, row.decision, row.applied_patch_id = "accepted", {"by": user_id, "at": iso(self.clock())}, \
            result.patch_id
        row.ops = ops
        return await self._decided(idea, row, user_id, "Accept.", result.patch_id, [f"Accepted {sid}: {row.title}"])

    async def reject(self, idea_id: str, sid: str, *, user_id: str, reason: str) -> dict:
        if not reason or not reason.strip():
            raise PatchRejected([Issue("envelope", "/reason", "a one-line reason is required to reject")])
        idea = await self._idea(idea_id)
        row = await self._row(idea_id, sid)
        row.status, row.decision = "rejected", {"by": user_id, "at": iso(self.clock()), "reason": reason.strip()}
        return await self._decided(idea, row, user_id, reason.strip(), None,
                                   [f"Rejected {sid}: {row.title}. Today's behaviour stays."])

    async def accept_remaining(self, idea_id: str, *, user_id: str) -> list[dict]:
        """'Accept all remaining': each is still accepted, and recorded, individually."""
        return [await self.accept(idea_id, r.id, user_id=user_id) for r in await self._rows(idea_id)
                if r.status not in DECIDED]

    async def edit(self, idea_id: str, sid: str, *, user_id: str, instruction: str) -> dict:
        """Revise one suggestion from the requester's instruction (scoped chat); guardrails apply again."""
        idea = await self._idea(idea_id)
        row = await self._row(idea_id, sid)
        as_is = await self.patches.get_ir(idea.as_is_process_id)
        to_be = await self.patches.get_ir(idea.to_be_process_id)
        revised, _ = await self.llm.complete_json("improve_edit", {
            "suggestion": row.as_suggestion(), "instruction": instruction, "to_be_view": _view(to_be),
            "id_conventions": {"suggestion_id": sid}}, SuggestedChange,
            correlation_id=self.patches.correlation_id, process_id=idea.to_be_process_id)
        turns, texts, _ = await self._evidence_texts(idea, as_is)
        s = self._from_proposal(revised, idea_id, sid, None)
        verdict = check(s, to_be, protected=protected_approvals(as_is), cases=cases_per_month(as_is),
                        turn_answers=turns, source_texts=texts, qualitative=revised.qualitative)
        if verdict.suggestion is None:
            raise PatchRejected([Issue("envelope", "/instruction", verdict.not_suggested["reason"])])
        v = verdict.suggestion
        row.kind, row.target_refs, row.title, row.change_summary = v["kind"], v["target_refs"], v["title"], \
            v["change_summary"]
        row.rationale, row.evidence, row.benefit, row.controls = v["rationale"], v["evidence"], v["benefit"], \
            v["controls"]
        row.risk, row.confidence, row.ops, row.status = v.get("risk"), v["confidence"], v["ops"], "edited"
        await write_audit(self.s, actor_kind="user", actor_id=user_id, action="suggestion.edited", target=sid,
                          process_id=idea.to_be_process_id, after={"instruction": instruction})
        await self.s.flush()
        return row.as_suggestion()

    async def _decided(self, idea: Idea, row: SuggestionRow, user_id: str, answer: str, patch_id: str | None,
                       captured: list[str]) -> dict:
        from services.intake.service import IntakeService
        await self.s.flush()
        rows = await self._rows(idea.id)
        accepted = [r for r in rows if r.status == "accepted"]
        idea.stats = {**(idea.stats or {}), "suggestions_accepted": len(accepted),
                      "suggestions_rejected": sum(r.status == "rejected" for r in rows),
                      "hours_saved_per_month": round(sum(r.benefit.get("hours_saved_per_month") or 0
                                                         for r in accepted), 1)}
        await write_audit(self.s, actor_kind="user", actor_id=user_id, action=f"suggestion.{row.status}",
                          target=row.id, process_id=idea.to_be_process_id, after=row.decision)
        intake = IntakeService(self.s, self.llm, clock=self.clock, correlation_id=self.patches.correlation_id)
        sess = await self._intake(idea)
        await intake.record_suggestion_decision(sess, row.id, row.status, answer, user_id, patch_id, captured,
                                                row.ops if row.status == "accepted" else None)
        if all(r.status in DECIDED for r in rows) and sess.phase == "improve":
            await intake.complete_improve(sess.id)
        return row.as_suggestion()

    # ------------------------------------------------------------------ report
    async def report(self, idea_id: str) -> str:
        idea = await self._idea(idea_id)
        return improvements_md(await self.patches.get_ir(idea.as_is_process_id),
                               await self.patches.get_ir(idea.to_be_process_id), await self.list_suggestions(idea_id))


def _view(ir: dict) -> dict:
    view = {k: v for k, v in ir.items() if k != "stories"}
    view["process"] = {k: v for k, v in ir["process"].items() if k not in ("version", "updated_at")}
    return view


def _row(s: dict, *, source: str) -> SuggestionRow:
    return SuggestionRow(id=s["suggestion_id"], idea_id=s["idea_id"], kind=s["kind"], target_refs=s["target_refs"],
                         title=s["title"], change_summary=s["change_summary"], rationale=s["rationale"],
                         evidence=s["evidence"], benefit=s["benefit"], controls=s["controls"], risk=s.get("risk"),
                         confidence=s["confidence"], status="proposed", decision=None, ops=s["ops"], source=source)

