"""M12 ideas workspace: the ideas list, idea detail, flows, comparison, stories, history and story-level edits.

Everything is read from the IR and the M5/M6/M11 tables, derived on demand (stories, DoR, stats), and every change
is a patch through M3 (CLAUDE.md rules 1-2).
"""
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from confidence_dor import band, closure_hash, evaluate_dor
from exporters import compare_rows, improvements_md
from flow_renderer import flow_json, hitl_summary, render_drawio, render_mermaid, thumbnail
from ir_core import Issue, PatchRejected
from ir_core.graph import closure, live
from services.common.db import utcnow
from services.gaps.store import stored_gaps, sync_gaps
from services.improve.db import SuggestionRow
from services.intake.coverage import coverage
from services.intake.db import IntakeSession, Signoff
from services.interviewer.ask import NewGap, ask_someone
from services.interviewer.db import Question, Sme
from services.ir_store.db import IrPatch
from services.ir_store.service import Actor, NotFound, PatchService, iso
from story_renderer import derive_stories, render_gherkin, render_markdown, render_story

from .db import Idea

PRIORITIES = ("must", "should", "could", "wont")
CONTROL_MODES = ("automated", "hitl_review", "human_task", "approval")
STORY_CONTROL = {"automated": "Automated (no person)", "hitl_review": "Automated + human review",
                 "human_task": "Human task", "approval": "Approval gate", None: "Not set"}


@dataclass
class StoryContext:
    """Everything needed to render an idea's stories at the current version."""

    ir: dict
    gaps: list[dict]
    questions: list[dict]
    stories: dict
    rows: dict  # story id → DoR row
    as_is: dict | None


class IdeasService:
    def __init__(self, session: AsyncSession, llm=None, *, clock=utcnow, correlation_id: str | None = None):
        self.s, self.llm, self.clock = session, llm, clock
        self.patches = PatchService(session, clock=clock, correlation_id=correlation_id)

    # ------------------------------------------------------------------ ideas
    async def idea(self, idea_id: str) -> Idea:
        idea = await self.s.get(Idea, idea_id)
        if idea is None:
            raise NotFound(f"idea {idea_id} not found")
        return idea

    @staticmethod
    def process_id(idea: Idea, variant: str | None = None) -> str:
        """The to-be once it exists (stories and refinement work on it), otherwise the as-is."""
        if variant == "as_is":
            if not idea.as_is_process_id:
                raise NotFound(f"{idea.id} has no as-is process")
            return idea.as_is_process_id
        if variant == "to_be" and not idea.to_be_process_id:
            raise NotFound(f"{idea.id} has no to-be process yet")
        return idea.to_be_process_id or idea.as_is_process_id

    async def list_ideas(self, *, status: str | None = None, owner: str | None = None, q: str | None = None,
                         tag: str | None = None) -> list[dict]:
        query = select(Idea).order_by(Idea.created_at.desc(), Idea.id)
        if status:
            query = query.where(Idea.status == status)
        if owner:
            query = query.where(Idea.owner_user_id == owner)
        if tag:
            query = query.where(Idea.tags.contains([tag]))
        if q:
            like = f"%{q}%"
            query = query.where(or_(Idea.title.ilike(like), Idea.summary.ilike(like)))
        return [await self.summary(i) for i in (await self.s.execute(query)).scalars()]

    async def summary(self, idea: Idea) -> dict:
        """idea.schema.json shape with live stats, plus what the list shows (waiting on, phase, thumbnail)."""
        ctx = await self.context(idea)
        suggestions = await self._suggestions(idea.id)
        stats = self._stats(ctx, suggestions)
        waiting = [{"text": oq["text"], "asked_to": oq["asked_to"]}
                   for s in ctx.stories.values() for oq in s["open_questions"] if oq["asked_to"]]
        sess = await self.s.get(IntakeSession, idea.session_id)
        out = {"idea_id": idea.id, "title": idea.title, "summary": idea.summary, "owner_user_id": idea.owner_user_id,
               "status": idea.status, "has_as_is": idea.has_as_is, "as_is_process_id": idea.as_is_process_id,
               "to_be_process_id": idea.to_be_process_id, "session_id": idea.session_id, "tags": list(idea.tags),
               "stats": stats, "created_at": iso(idea.created_at), "updated_at": iso(idea.updated_at)}
        return {**out, "phase": sess.phase if sess else None,
                "waiting_on": sorted({w["asked_to"] for w in waiting}), "thumbnail": thumbnail(ctx.ir)}

    @staticmethod
    def _stats(ctx: StoryContext, suggestions: list[SuggestionRow]) -> dict:
        accepted = [x for x in suggestions if x.status == "accepted"]
        return {"stories": len(ctx.stories),
                "stories_ready": sum(r["status"] in ("ready", "waived") for r in ctx.rows.values()),
                "open_questions": sum(len(s["open_questions"]) for s in ctx.stories.values()),
                "suggestions_accepted": len(accepted),
                "suggestions_rejected": sum(x.status == "rejected" for x in suggestions),
                "hours_saved_per_month": round(sum(x.benefit.get("hours_saved_per_month") or 0 for x in accepted), 1)
                if suggestions else None,
                "coverage": coverage(ctx.ir)["percent"]}

    async def overview(self, idea_id: str) -> dict:
        idea = await self.idea(idea_id)
        ctx = await self.context(idea)
        ir = ctx.ir
        personas = {k: p["name"] for k, p in live(ir, "personas").items()}
        return {**await self.summary(idea),
                "process": {"id": ir["process"]["id"], "name": ir["process"]["name"],
                            "variant": ir["process"]["variant"], "version": ir["process"]["version"],
                            "description": ir["process"].get("description")},
                "goals": [{"id": k, "statement": g["statement"], "metrics": g["metrics"],
                           "beneficiaries": [personas[p] for p in g.get("persona_ids", []) if p in personas]}
                          for k, g in live(ir, "goals").items()],
                "beneficiaries": list(personas.values()), "scope": ir["scope"],
                "nfrs": [{"id": k, "category": n["category"], "statement": n["statement"], "measure": n.get("measure")}
                         for k, n in live(ir, "nfrs").items()],
                "open_questions": [{"story_id": sid, **oq} for sid, s in ctx.stories.items()
                                   for oq in s["open_questions"]]}

    # ------------------------------------------------------------------ stories
    async def context(self, idea: Idea, variant: str | None = None) -> StoryContext:
        pid = self.process_id(idea, variant)
        ir = await self.patches.get_ir(pid)
        gaps = [g.as_gap() for g in await stored_gaps(self.s, pid)]
        questions = [{"gap_ids": q.gap_ids, "sme_id": q.sme_id or q.assignee_user_id, "status": q.status}
                     for q in (await self.s.execute(select(Question).where(Question.process_id == pid))).scalars()]
        try:
            stories = derive_stories(ir, gaps, questions, version=ir["process"]["version"])
        except ValueError:  # a task without an actor: no stories until someone is named (M5 node_without_actor)
            stories = {}
        signed = {r.story_id: r.closure_hash for r in
                  (await self.s.execute(select(Signoff).where(Signoff.process_id == pid))).scalars()}
        valid = {sid for sid, s in stories.items() if signed.get(sid) == closure_hash(ir, s)}  # M8: hash unchanged
        rows = {r["story_id"]: r for r in evaluate_dor(ir, stories, gaps, signoffs=valid)}
        ir = {**ir, "stories": stories}
        as_is = await self.patches.get_ir(idea.as_is_process_id) if idea.to_be_process_id and idea.as_is_process_id \
            else None
        return StoryContext(ir, gaps, questions, stories, rows, as_is)

    async def stories(self, idea_id: str) -> list[dict]:
        ctx = await self.context(await self.idea(idea_id))
        return [self._story_row(ctx, sid, s) for sid, s in ctx.stories.items()]

    @staticmethod
    def _story_row(ctx: StoryContext, sid: str, s: dict) -> dict:
        change = s.get("change")
        return {"story_id": sid, "title": s["title"], "priority": s["priority"],
                "control": STORY_CONTROL[s["human_control"]["mode"]], "control_mode": s["human_control"]["mode"],
                "confidence": s["confidence"], "band": band(s["confidence"]), "dor_status": s["dor_status"],
                "failed_checks": ctx.rows[sid]["failed_checks"], "open_questions": len(s["open_questions"]),
                "change": f"{change['suggestion_id']}: {change['kind'].replace('_', ' ')}" if change else None,
                "node_ids": s["node_ids"]}

    async def story(self, idea_id: str, sid: str) -> dict:
        idea = await self.idea(idea_id)
        ctx = await self.context(idea)
        if sid not in ctx.stories:
            raise NotFound(f"story {sid} not found in {idea_id}")
        s = ctx.stories[sid]
        task = ctx.ir["nodes"][s["node_ids"][0]]
        return {**self._story_row(ctx, sid, s), "story": s, "markdown": render_story(ctx.ir, sid, ctx.rows[sid]),
                "dor": ctx.rows[sid], "process_id": ctx.ir["process"]["id"], "version": ctx.ir["process"]["version"],
                "editable": {"task_id": s["node_ids"][0], "outcome": task.get("outcome"),
                             "hitl": task.get("hitl", {}),
                             "acceptance_criteria": {a: {k: ctx.ir["acceptance_criteria"][a][k]
                                                         for k in ("title", "given", "when", "then", "kind")}
                                                     for a in s["ac_ids"]}}}

    async def stories_markdown(self, idea_id: str) -> str:
        idea = await self.idea(idea_id)
        ctx = await self.context(idea)
        v = ctx.ir["process"]
        return render_markdown(ctx.ir, list(ctx.rows.values()), as_is=ctx.as_is,
                               origin=f"the {v['variant'].replace('_', '-')} process (v{v['version']})")

    async def feature(self, idea_id: str) -> str:
        ctx = await self.context(await self.idea(idea_id))
        return render_gherkin(ctx.ir)

    # ------------------------------------------------------------------ flows
    async def flow(self, idea_id: str, variant: str | None, fmt: str):
        idea = await self.idea(idea_id)
        ir = await self.patches.get_ir(self.process_id(idea, variant))
        if fmt == "drawio":
            return render_drawio(ir)
        if fmt == "mermaid":
            return render_mermaid(ir)
        return {**flow_json(ir), "hitl": hitl_summary(ir)}

    async def compare(self, idea_id: str) -> dict:
        idea = await self.idea(idea_id)
        if not (idea.as_is_process_id and idea.to_be_process_id):
            raise NotFound(f"{idea_id} needs both an as-is and a to-be to compare")
        as_is = await self.patches.get_ir(idea.as_is_process_id)
        to_be = await self.patches.get_ir(idea.to_be_process_id)
        nodes = {n["name"]: k for k, n in to_be["nodes"].items()}
        rows = [{"node_id": nodes.get(r[0]), "step": r[0], "today": r[1], "minutes_today": r[2] or None,
                 "to_be": r[3], "change": r[4]} for r in compare_rows(as_is, to_be)]
        return {"rows": rows, "as_is": flow_json(as_is), "to_be": flow_json(to_be)}

    async def improvements_report(self, idea_id: str) -> str:
        idea = await self.idea(idea_id)
        rows = await self._suggestions(idea_id)
        return improvements_md(await self.patches.get_ir(idea.as_is_process_id),
                               await self.patches.get_ir(idea.to_be_process_id), [r.as_suggestion() for r in rows])

    async def _suggestions(self, idea_id: str) -> list[SuggestionRow]:
        q = select(SuggestionRow).where(SuggestionRow.idea_id == idea_id).order_by(SuggestionRow.id)
        return list((await self.s.execute(q)).scalars())

    # ------------------------------------------------------------------ history and undo
    async def history(self, idea_id: str, sid: str) -> list[dict]:
        """Applied patches that touched the story's closure, newest first (M12 version history)."""
        idea = await self.idea(idea_id)
        ctx = await self.context(idea)
        if sid not in ctx.stories:
            raise NotFound(f"story {sid} not found in {idea_id}")
        ids = closure(ctx.ir, ctx.stories[sid]["node_ids"])
        q = select(IrPatch).where(IrPatch.process_id == ctx.ir["process"]["id"], IrPatch.status == "applied") \
            .order_by(IrPatch.applied_version.desc())
        out = []
        for p in (await self.s.execute(q)).scalars():
            touched = {path.split("/")[2] for path in p.changed_paths if path.count("/") >= 2}
            if touched & ids:
                out.append({"patch_id": p.id, "version": p.applied_version, "reason": p.reason,
                            "author": {"kind": p.author_kind, "id": p.author_id},
                            "at": iso(p.updated_at), "changed_paths": p.changed_paths,
                            "touched": sorted(touched & ids)})
        return out

    async def undo(self, idea_id: str, patch_id: str, *, user_id: str) -> dict:
        idea = await self.idea(idea_id)
        patch = await self.patches.get_patch(patch_id)
        if patch.process_id not in (idea.as_is_process_id, idea.to_be_process_id):
            raise NotFound(f"patch {patch_id} is not part of {idea_id}")
        result = await self.patches.revert(patch_id, actor=Actor("user", user_id))
        await self._after_change(patch.process_id, result.patch_id)
        return {"patch_id": result.patch_id, "status": result.status, "to_version": result.to_version,
                "conflicting_paths": result.conflicting_paths}

    async def _after_change(self, process_id: str, patch_id: str | None) -> None:
        """M5 re-runs after any change, so DoR and open questions are current (M8 is derived on read)."""
        await sync_gaps(self.s, await self.patches.get_ir(process_id), patch_id=patch_id)

    # ------------------------------------------------------------------ inline edits and ask someone
    async def edit(self, idea_id: str, sid: str, *, user_id: str, field: str, value, ac_id: str | None = None,
                   part: str | None = None) -> dict:
        """Fields that map 1:1 to the IR (M12 Story detail, way 2). Each edit is one user patch."""
        idea = await self.idea(idea_id)
        ctx = await self.context(idea)
        if sid not in ctx.stories:
            raise NotFound(f"story {sid} not found in {idea_id}")
        task = ctx.stories[sid]["node_ids"][0]
        node = ctx.ir["nodes"][task]
        ops = self._edit_ops(ctx, sid, task, node, field, value, ac_id, part)
        proc = await self.patches.get_process(ctx.ir["process"]["id"])
        result = await self.patches.submit({
            "patch_id": f"edit_{sid}_{field}_{proc.current_version + 1}"[:60], "process_id": proc.id,
            "base_version": proc.current_version, "ops": ops, "author": {"kind": "user", "id": user_id},
            "reason": f"Edited {field.replace('_', ' ')} of {ctx.stories[sid]['title']}", "auto_apply": True,
            "status": "proposed"}, actor=Actor("user", user_id))
        await self._after_change(proc.id, result.patch_id)
        return await self.story(idea_id, sid)

    @staticmethod
    def _edit_ops(ctx, sid, task, node, field, value, ac_id, part) -> list[dict]:
        def bad(message):
            return PatchRejected([Issue("envelope", f"/{field}", message)])

        if field == "priority":
            if value not in PRIORITIES:
                raise bad(f"priority must be one of {', '.join(PRIORITIES)}")
            return [{"op": "replace" if "priority" in node else "add", "path": f"/nodes/{task}/priority",
                     "value": value}]
        if field == "outcome":
            if not isinstance(value, str) or not value.strip():
                raise bad("outcome must be a sentence")
            return [{"op": "replace" if "outcome" in node else "add", "path": f"/nodes/{task}/outcome",
                     "value": value.strip()}]
        if field == "control_mode":
            mode = value.get("mode") if isinstance(value, dict) else value
            if mode not in CONTROL_MODES:
                raise bad(f"control must be one of {', '.join(CONTROL_MODES)}")
            hitl = {"mode": mode}
            if mode in ("hitl_review", "approval"):
                hitl["actor_id"] = (value.get("actor_id") if isinstance(value, dict) else None) or node.get("actor_id")
            if mode == "hitl_review":
                hitl["trigger"] = (value.get("trigger") if isinstance(value, dict) else None) or "on_exception"
            if mode == "approval":
                criteria = value.get("criteria") if isinstance(value, dict) else None
                if not criteria:
                    raise bad("an approval gate needs the criteria the approver checks")
                hitl["criteria"] = criteria
            return [{"op": "replace" if "hitl" in node else "add", "path": f"/nodes/{task}/hitl", "value": hitl}]
        if field == "acceptance_criterion":
            if ac_id not in ctx.stories[sid]["ac_ids"]:
                raise bad(f"{ac_id} is not one of this story's acceptance criteria")
            if part == "title":
                return [{"op": "replace", "path": f"/acceptance_criteria/{ac_id}/title", "value": str(value)}]
            if part not in ("given", "when", "then") or not isinstance(value, list) or not all(
                    isinstance(v, str) and v.strip() for v in value) or not value:
                raise bad("given, when and then each need at least one line")
            return [{"op": "replace", "path": f"/acceptance_criteria/{ac_id}/{part}", "value": value}]
        raise bad(f"{field} cannot be edited here; use the refine chat")

    async def ask(self, idea_id: str, sid: str, *, user_id: str, text: str, sme_id: str | None = None,
                  ask_user_id: str | None = None) -> dict:
        """Ask someone about this story: an M6 question, shown as the story's open question (M12 way 3)."""
        idea = await self.idea(idea_id)
        ctx = await self.context(idea)
        if sid not in ctx.stories:
            raise NotFound(f"story {sid} not found in {idea_id}")
        if not text or not text.strip():
            raise PatchRejected([Issue("envelope", "/text", "write the question to ask")])
        task = ctx.stories[sid]["node_ids"][0]
        n = len([g for g in ctx.gaps if g["gap_id"].startswith(f"gap_ask_{sid}")]) + 1
        _, _, captured = await ask_someone(
            self.s, process_id=ctx.ir["process"]["id"], ir_version=ctx.ir["process"]["version"], sme_id=sme_id,
            asked_by=user_id, text=text.strip(), context=f"About the story '{ctx.stories[sid]['title']}'",
            answer_type="free_text", options=[], now=self.clock(),
            new_gap=NewGap(gap_id=f"gap_ask_{sid}_{n}", type="unclear_business_rule", target_refs=[f"/nodes/{task}"],
                           title=text.strip(), why_it_matters="Asked from the story detail.", topic="story"),
            correlation_id=self.patches.correlation_id, user_id=ask_user_id)
        return {"captured": captured, "story": await self.story(idea_id, sid)}

    async def smes(self) -> list[dict]:
        rows = (await self.s.execute(select(Sme).order_by(Sme.name))).scalars()
        return [{"sme_id": r.id, "name": r.name, "role_title": r.role_title} for r in rows]

