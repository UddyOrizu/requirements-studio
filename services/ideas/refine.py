"""M12 story refinement: an instruction becomes IR ops (prompts/story_refine.md), shown as a preview, then applied.

Rules (M12 "Refinement rules"): ops stay inside the story's closure, except the split/merge rewiring of adjacent
edges; ambiguous instructions get one clarifying question; a question is answered without changes; provenance cites
the intake source at the instruction's turn with a verbatim excerpt (as in M0).
"""
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from flow_renderer import flow_json
from ir_core import Issue, PatchRejected, apply_patch
from ir_core.graph import closure, live
from ir_core.ids import ELEMENT_COLLECTIONS, PREFIX_TO_COLLECTION
from ir_core.llm_models import StoryRefinement
from services.common.db import utcnow
from services.intake.db import IntakeSession, StoryRefinementRow
from services.intake.service import IntakeService, provenance_refs
from services.ir_store.service import Actor, Conflict, NotFound, iso
from story_renderer import derive_stories, render_story

from .service import IdeasService

CREATABLE = ("/acceptance_criteria", "/exceptions", "/slas", "/edges", "/nodes", "/glossary")


class OutOfScope(PatchRejected):
    """The instruction would change elements outside the story (M12 AC-M12-5)."""


def scope_problems(ir: dict, ops: list[dict], story_nodes: list[str]) -> list[str]:
    """Paths an op may not touch: outside the story's closure, unless created here or part of a split/merge."""
    cl = closure(ir, story_nodes)
    created = {(p[1], p[2]) for op in ops for p in [op["path"].split("/")]
               if op["op"] == "add" and len(p) == 3 and p[1] in ELEMENT_COLLECTIONS}
    created_ids = {eid for _, eid in created}
    removed_tasks = {p[2] for op in ops for p in [op["path"].split("/")]
                     if op["op"] == "remove" and len(p) == 3 and p[1] == "nodes"
                     and ir["nodes"].get(p[2], {}).get("type") == "task"}
    new_tasks = {eid for coll, eid in created if coll == "nodes"}
    reshaping = bool(removed_tasks | new_tasks)  # a split or a merge
    adjacent = {k for k, e in live(ir, "edges").items() if {e["from"], e["to"]} & set(story_nodes)}
    neighbours = {e["to"] if e["from"] in story_nodes else e["from"] for k, e in live(ir, "edges").items()
                  if k in adjacent}
    merged = closure(ir, list(removed_tasks & neighbours)) if removed_tasks & neighbours else set()
    problems = []
    for op in ops:
        for path in (op["path"], op.get("from")):
            if not path:
                continue
            parts = path.split("/")
            coll, eid = parts[1], parts[2] if len(parts) > 2 else ""
            if coll not in ELEMENT_COLLECTIONS or not eid:
                problems.append(path)
            elif eid in cl or eid in created_ids:
                continue
            elif reshaping and (eid in adjacent or eid in merged):
                continue
            else:
                problems.append(path)
    return sorted(set(problems))


class RefinementService:
    def __init__(self, session: AsyncSession, llm, *, clock=utcnow, correlation_id: str | None = None):
        self.s, self.llm, self.clock = session, llm, clock
        self.ideas = IdeasService(session, llm, clock=clock, correlation_id=correlation_id)
        self.patches = self.ideas.patches

    async def preview(self, idea_id: str, sid: str, *, instruction: str, user_id: str) -> dict:
        idea = await self.ideas.idea(idea_id)
        ctx = await self.ideas.context(idea)
        if sid not in ctx.stories:
            raise NotFound(f"story {sid} not found in {idea_id}")
        if not instruction or not instruction.strip():
            raise PatchRejected([Issue("envelope", "/instruction", "write what you want to change")])
        sess = await self.s.get(IntakeSession, idea.session_id)
        if sess is None or not sess.source_id:
            raise Conflict("/problems/no-session", "refinement needs the idea's conversation (its intake source)")
        story = ctx.stories[sid]
        ir = ctx.ir
        cl = closure(ir, story["node_ids"])
        turn_id = f"T{(sess.state or {}).get('turns', 0) + 1}"
        neighbours = {e["to"] if e["from"] in story["node_ids"] else e["from"]
                      for e in live(ir, "edges").values() if {e["from"], e["to"]} & set(story["node_ids"])}
        result, _ = await self.llm.complete_json("story_refine", {
            "instruction": instruction,
            "turn_id": turn_id,
            "source_id": sess.source_id,
            "story": {k: v for k, v in story.items() if k not in ("rendered_from_version", "confidence")},
            "closure": {i: ir[PREFIX_TO_COLLECTION[i.split("_")[0]]][i] for i in sorted(cl)},
            "neighbours": {n: {"name": ir["nodes"][n]["name"], "type": ir["nodes"][n]["type"]}
                           for n in sorted(neighbours - set(story["node_ids"]))},
            "allowed_paths": sorted({f"/{PREFIX_TO_COLLECTION[i.split('_')[0]]}/{i}" for i in cl} | set(CREATABLE)),
            "id_conventions": {"pattern": "<prefix>_<snake_case>", "prefixes": PREFIX_TO_COLLECTION},
        }, StoryRefinement, correlation_id=self.patches.correlation_id, process_id=ir["process"]["id"])

        base = {"story_id": sid, "instruction": instruction, "turn_id": turn_id, "summary": result.summary}
        if not result.ops:
            return {**base, "kind": "clarify" if result.clarifying_question else "answer",
                    "question": result.clarifying_question, "answer": result.answer}

        ops = [op.model_dump(by_alias=True, exclude_unset=True) for op in result.ops]
        problems = [Issue("envelope", f"/ops/{i}", f"excerpt {ref.get('excerpt')!r} is not verbatim in the instruction")
                    for i, op in enumerate(ops) for ref in provenance_refs(op.get("value"))
                    if ref["source_id"] == sess.source_id and ref.get("excerpt") not in instruction]
        if problems:
            raise PatchRejected(problems)
        if outside := scope_problems(ir, ops, story["node_ids"]):
            names = [self._describe(ir, p) for p in outside]
            raise OutOfScope([Issue("scope", p, f"this would change something outside the story: {n}")
                              for p, n in zip(outside, names, strict=True)])
        base_ir = {k: v for k, v in ir.items() if k != "stories"}
        after = apply_patch(base_ir, {"patch_id": "preview", "process_id": ir["process"]["id"],
                                      "base_version": ir["process"]["version"], "ops": ops,
                                      "author": {"kind": "user", "id": user_id}, "reason": "preview",
                                      "auto_apply": False, "status": "proposed"})
        after_stories = derive_stories(after, ctx.gaps, ctx.questions, version=ir["process"]["version"] + 1)
        changed_nodes = set(story["node_ids"]) | {p.split("/")[2] for op in ops for p in [op["path"]]
                                                  if p.startswith("/nodes/") and p.count("/") >= 2}
        affected = [k for k, st in after_stories.items() if set(st["node_ids"]) & changed_nodes]
        after["stories"] = after_stories
        preview = {**base, "kind": "preview", "ops": ops, "base_version": ir["process"]["version"],
                   "story_before": render_story(ir, sid, ctx.rows[sid]),
                   "stories_after": {k: render_story(after, k, None) for k in affected},
                   "flow_changes": flow_changes(base_ir, after)}
        row = StoryRefinementRow(process_id=ir["process"]["id"], story_id=sid, instruction=instruction,
                                 preview=preview, status="previewed", by=user_id, at=self.clock())
        self.s.add(row)
        await self.s.flush()
        return {**preview, "preview_id": str(row.id)}

    @staticmethod
    def _describe(ir: dict, path: str) -> str:
        parts = path.split("/")
        x = ir.get(parts[1], {}).get(parts[2] if len(parts) > 2 else "", {})
        name = x.get("name") or x.get("title") or x.get("term") or (parts[2] if len(parts) > 2 else path)
        return f"{name} ({path})"

    async def apply(self, idea_id: str, sid: str, preview_id: str, *, user_id: str) -> dict:
        idea = await self.ideas.idea(idea_id)
        row = await self.s.get(StoryRefinementRow, UUID(preview_id), with_for_update=True)
        if row is None or row.story_id != sid:
            raise NotFound(f"preview {preview_id} not found for {sid}")
        if row.status != "previewed":
            raise Conflict("/problems/preview-used", f"this preview was already {row.status}")
        p = row.preview
        sess = await self.s.get(IntakeSession, idea.session_id, with_for_update=True)
        if f"T{(sess.state or {}).get('turns', 0) + 1}" != p["turn_id"]:
            raise Conflict("/problems/preview-stale", "the conversation moved on since this preview; preview again")
        result = await self.patches.submit({
            "patch_id": f"refine_{sid}_{p['turn_id'].lower()}_{str(row.id)[-8:]}"[:60], "process_id": row.process_id,
            "base_version": p["base_version"], "ops": p["ops"], "author": {"kind": "user", "id": user_id},
            "reason": f"{p['turn_id']}: refine {sid}: {row.instruction}"[:500], "auto_apply": True,
            "status": "proposed", "evidence": {"source_ids": [sess.source_id]}}, actor=Actor("user", user_id))
        if result.status != "applied":
            raise Conflict("/problems/patch-conflict", "the story changed since the preview; preview again",
                           conflicting_paths=result.conflicting_paths)
        row.status, row.patch_id = "applied", result.patch_id
        state = dict(sess.state or {})
        state["turns"] = state.get("turns", 0) + 1
        sess.state = state
        intake = IntakeService(self.s, self.llm, clock=self.clock, correlation_id=self.patches.correlation_id)
        await intake._new_entry(sess, "story_refinement", target={"kind": "story", "id": sid}, turn=p["turn_id"],
                                answer_text=row.instruction, patch_id=result.patch_id, captured=p["summary"],
                                payload={"story_id": sid, "answer_by": user_id})
        await self.ideas._after_change(row.process_id, result.patch_id)
        ctx = await self.ideas.context(idea)
        affected = [k for k in p["stories_after"] if k in ctx.stories]
        return {"patch_id": result.patch_id, "to_version": result.to_version, "story_ids": affected,
                "at": iso(self.clock())}


def flow_changes(before: dict, after: dict) -> list[str]:
    """Plain-English differences between two flows: steps, controls, human queues, connections."""
    b, a = flow_json(before), flow_json(after)
    bn, an = {n["id"]: n for n in b["nodes"]}, {n["id"]: n for n in a["nodes"]}
    lanes = {ln["id"]: ln["name"] for ln in a["lanes"] + b["lanes"]}
    out: list[str] = []
    for k in an.keys() - bn.keys():
        n = an[k]
        what = "human queue" if n["type"] == "queue" else n["type"]
        out.append(f"New {what} '{n['lines'][1] if n['type'] == 'queue' else n['lines'][-1]}' "
                   f"in the {lanes.get(n['lane'], n['lane'])} lane")
    for k in bn.keys() - an.keys():
        out.append(f"Removed '{bn[k]['lines'][1] if len(bn[k]['lines']) > 1 else bn[k]['lines'][0]}'")
    for k in an.keys() & bn.keys():
        if an[k]["control"] != bn[k]["control"]:
            out.append(f"'{an[k]['lines'][1] if len(an[k]['lines']) > 1 else k}': control "
                       f"{bn[k]['control']} → {an[k]['control']}")
    be = {(e["source"], e["target"]) for e in b["edges"]}
    ae = {(e["source"], e["target"]) for e in a["edges"]}
    out += [f"New connection {s} → {t}" for s, t in sorted(ae - be) if not t.startswith("queue_")]
    out += [f"Removed connection {s} → {t}" for s, t in sorted(be - ae) if not t.startswith("queue_")]
    return sorted(out)

