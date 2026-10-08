"""M3 Patch Service: the only code that writes IR versions (CLAUDE.md rules 1-2).

Methods run inside the caller's transaction and never commit: the API commits once per request, so the IR version,
patch status, audit row and outbox event land together or not at all. Outcomes the caller must persist (a patch
marked conflicted) are returned, not raised; errors that change nothing raise PatchRejected (422), NotFound (404) or
Conflict (409).
"""
import copy
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

import jsonpatch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from confidence_dor import score_elements
from ir_core import (
    Issue,
    PatchRejected,
    apply_patch,
    changed_paths,
    conflicting_paths,
    forbidden_ops,
    ir_hash,
    validate_integrity,
    validate_schema,
)
from ir_core.ids import DEAD_STATUSES, ELEMENT_COLLECTIONS
from services.common.db import utcnow
from services.common.events import EventEnvelope
from services.common.outbox import enqueue_event
from services.common.uuid7 import uuid7_str
from services.ideas.db import Idea
from services.identity_audit.audit import write_audit

from .db import IrPatch, IrVersion, Process
from .policy import answer_confirmations, review_decision


class NotFound(LookupError):
    pass


class Conflict(Exception):
    """409 with an RFC 7807 problem type and extra members."""

    def __init__(self, problem: str, title: str, **extra: Any):
        super().__init__(title)
        self.problem, self.title, self.extra = problem, title, extra


@dataclass(frozen=True)
class Actor:
    kind: Literal["user", "agent", "system"]
    id: str


@dataclass
class PatchResult:
    patch_id: str
    status: str  # applied | proposed | conflicted
    process_id: str
    base_version: int
    current_version: int
    to_version: int | None = None
    changed_paths: list[str] = field(default_factory=list)
    conflicting_paths: list[str] = field(default_factory=list)


@dataclass
class ForkResult:
    as_is_process_id: str
    to_be_process_id: str
    # Same shape as the intake session timeline's `fork` object, so M0 can record it as-is.
    fork: dict


# (session, patch envelope) → (answerer_id, routed_sme_id). M6 supplies the real lookup; until then nobody qualifies
# for auto-accept, which matches the policy default (off).
AnswerAttribution = Callable[[AsyncSession, dict], Awaitable[tuple[str | None, str | None]]]


async def no_attribution(session: AsyncSession, patch: dict) -> tuple[str | None, str | None]:
    return None, None


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def empty_ir(process: dict) -> dict:
    return {"ir_version": "1.1", "process": process, "sources": {}, **{c: {} for c in ELEMENT_COLLECTIONS},
            "scope": {"in": [], "out": [], "assumptions": [], "constraints": [], "confirmed_none": []}}


def content_view(ir: dict) -> dict:
    """The IR without derived stories and the Patch Service's managed fields: what a revert restores."""
    view = {k: v for k, v in ir.items() if k != "stories"}
    view["process"] = {k: v for k, v in ir["process"].items() if k not in ("version", "updated_at")}
    return view


def to_be_id_for(as_is_id: str) -> str:
    """M11 convention: <as-is id>_to_be, dropping a trailing _as_is (proc_client_kyc_as_is → proc_client_kyc_to_be)."""
    return as_is_id.removesuffix("_as_is") + "_to_be"


class PatchService:
    def __init__(self, session: AsyncSession, *, clock: Callable[[], datetime] = utcnow,
                 answer_attribution: AnswerAttribution = no_attribution, correlation_id: str | None = None):
        self.s = session
        self.clock = clock
        self.answer_attribution = answer_attribution
        self.correlation_id = correlation_id or uuid7_str()

    # ------------------------------------------------------------------ reads
    async def get_process(self, process_id: str, *, lock: bool = False) -> Process:
        q = select(Process).where(Process.id == process_id)
        proc = (await self.s.execute(q.with_for_update() if lock else q)).scalar_one_or_none()
        if proc is None:
            raise NotFound(f"process {process_id} not found")
        return proc

    async def list_processes(self, idea_id: str | None = None) -> list[Process]:
        q = select(Process).order_by(Process.id)
        if idea_id:
            q = q.where(Process.idea_id == idea_id)
        return list((await self.s.execute(q)).scalars())

    async def get_ir(self, process_id: str, version: int | None = None) -> dict:
        proc = await self.get_process(process_id)
        row = await self.s.get(IrVersion, (process_id, proc.current_version if version is None else version))
        if row is None:
            raise NotFound(f"{process_id} has no version {version}")
        return row.snapshot

    async def diff(self, process_id: str, from_version: int, to_version: int) -> list[dict]:
        a, b = await self.get_ir(process_id, from_version), await self.get_ir(process_id, to_version)
        return jsonpatch.make_patch(a, b).patch

    async def get_patch(self, patch_id: str, *, lock: bool = False) -> IrPatch:
        q = select(IrPatch).where(IrPatch.id == patch_id)
        row = (await self.s.execute(q.with_for_update() if lock else q)).scalar_one_or_none()
        if row is None:
            raise NotFound(f"patch {patch_id} not found")
        return row

    async def list_patches(self, process_id: str, status: str | None = None) -> list[IrPatch]:
        await self.get_process(process_id)
        q = select(IrPatch).where(IrPatch.process_id == process_id).order_by(IrPatch.created_at, IrPatch.id)
        if status:
            q = q.where(IrPatch.status == status)
        return list((await self.s.execute(q)).scalars())

    # ------------------------------------------------------------------ processes
    async def create_process(self, *, name: str, owner_user_id: str, actor: Actor, domain: str | None = None,
                             description: str | None = None, variant: str = "as_is", idea_id: str | None = None,
                             process_id: str | None = None) -> dict:
        """POST /processes: a new process at IR v0 (empty, schema-valid)."""
        header = {"id": process_id or await self._free_process_id(name), "name": name,
                  "owner_user_id": owner_user_id, "status": "draft", "version": 0,
                  "updated_at": iso(self.clock()), "variant": variant}
        if description:
            header["description"] = description
        if domain:
            header["domain"] = domain
        if idea_id:
            header["idea_id"] = idea_id
        return await self._insert_process(empty_ir(header), actor, action="process.created")

    async def import_process(self, ir: dict, *, actor: Actor) -> dict:
        """Seed a process from a complete IR at its own process.version (document-led imports, fixtures).

        Validated like any patch result and re-scored; no patch history exists before that version.
        """
        return await self._insert_process(copy.deepcopy(ir), actor, action="process.imported")

    async def _free_process_id(self, name: str) -> str:
        base = "proc_" + (re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:50] or "process")
        candidate, n = base, 1
        while await self.s.get(Process, candidate) is not None:
            n += 1
            candidate = f"{base}_{n}"
        return candidate

    async def _insert_process(self, ir: dict, actor: Actor, *, action: str, frozen: bool = False) -> dict:
        header = ir["process"]
        if await self.s.get(Process, header["id"]) is not None:
            raise Conflict("/problems/process-exists", f"process {header['id']} already exists")
        idea_id = header.get("idea_id")
        if idea_id and await self.s.get(Idea, idea_id) is None:
            raise PatchRejected([Issue("envelope", "/process/idea_id", f"unknown idea {idea_id}")])
        self._validate(ir)
        score_elements(ir)
        self.s.add(Process(id=header["id"], name=header["name"], domain=header.get("domain"),
                           description=header.get("description"), owner_user_id=header["owner_user_id"],
                           status=header["status"], current_version=header["version"], idea_id=idea_id,
                           variant=header["variant"], settings={"auto_accept": False}))
        await self.s.flush()
        self.s.add(IrVersion(process_id=header["id"], version=header["version"], snapshot=ir, ir_hash=ir_hash(ir)))
        await write_audit(self.s, actor_kind=actor.kind, actor_id=actor.id, action=action, target=header["id"],
                          process_id=header["id"], after={"version": header["version"], "variant": header["variant"]})
        await self.s.flush()
        return ir

    # ------------------------------------------------------------------ patches
    async def submit(self, patch: dict, *, actor: Actor) -> PatchResult:
        """POST /processes/{pid}/patches → applied (201) | proposed (202) | conflicted (409); 422 raises."""
        if issues := forbidden_ops(patch.get("ops") or []):
            raise PatchRejected(issues)
        if issues := validate_schema(patch, "patch"):
            raise PatchRejected([Issue("envelope", i.path, i.message) for i in issues])
        proc = await self.get_process(patch["process_id"], lock=True)
        self._check_not_frozen(proc)

        existing = await self.s.get(IrPatch, patch["patch_id"])
        if existing is not None:  # idempotent resubmission
            if existing.process_id == proc.id and existing.ops == patch["ops"]:
                return self._result(existing, proc)
            raise Conflict("/problems/patch-id-reused", f"patch_id {patch['patch_id']} is already used")
        if patch["base_version"] > proc.current_version:
            raise PatchRejected([Issue("envelope", "/base_version",
                                       f"base_version {patch['base_version']} is ahead of current "
                                       f"version {proc.current_version}")])

        current = await self.get_ir(proc.id)
        answerer, routed = await self.answer_attribution(self.s, patch)
        decision = review_decision(patch, current, current_version=proc.current_version,
                                   auto_accept_enabled=bool((proc.settings or {}).get("auto_accept")),
                                   answerer_id=answerer, routed_sme_id=routed)
        row = IrPatch(id=patch["patch_id"], process_id=proc.id, base_version=patch["base_version"], ops=patch["ops"],
                      author_kind=patch["author"]["kind"], author_id=patch["author"]["id"], reason=patch["reason"],
                      evidence=patch.get("evidence"), interpretation_confidence=patch.get("interpretation_confidence"),
                      auto_apply=patch["auto_apply"], status="proposed", reviewed_by=patch.get("reviewed_by"),
                      changed_paths=changed_paths(patch["ops"]))
        # Conflicts are recorded; invalid patches are not (nothing is added before the dry run passes).
        if conflicts := await self._conflicts(proc, row):
            return await self._mark_conflicted(proc, row, conflicts)
        self._dry_run(current, row)
        self.s.add(row)
        await self.s.flush()
        if decision == "apply":
            return await self._apply(proc, row, actor)

        await write_audit(self.s, actor_kind=actor.kind, actor_id=actor.id, action="patch.proposed", target=row.id,
                          process_id=proc.id, after={"base_version": row.base_version, "ops": row.ops})
        await enqueue_event(self.s, self._event("patch.proposed", proc, None, {
            "patch_id": row.id, "author": {"kind": row.author_kind, "id": row.author_id},
            "reviewer_ids": [proc.owner_user_id]}))
        return self._result(row, proc)

    async def accept(self, patch_id: str, *, reviewer: Actor, ops: list[dict] | None = None,
                     reason: str | None = None) -> PatchResult:
        """Accept a proposed patch, or edit-and-accept: `ops` become a new user patch that supersedes it."""
        original = await self.get_patch(patch_id, lock=True)
        proc = await self.get_process(original.process_id, lock=True)
        self._check_not_frozen(proc)
        if original.status != "proposed":
            raise Conflict("/problems/patch-not-proposed", f"patch {patch_id} is {original.status}",
                           patch_status=original.status)
        now = self.clock()
        if ops is None:
            original.reviewed_by, original.reviewed_at = reviewer.id, now
            await write_audit(self.s, actor_kind=reviewer.kind, actor_id=reviewer.id, action="patch.accepted",
                              target=original.id, process_id=proc.id)
            return await self._apply(proc, original, reviewer)

        edited = {"patch_id": uuid7_str(), "process_id": proc.id, "base_version": original.base_version, "ops": ops,
                  "author": {"kind": "user", "id": reviewer.id},
                  "reason": reason or f"Edited and accepted from {original.id}", "auto_apply": True,
                  "status": "proposed", **({"evidence": original.evidence} if original.evidence else {})}
        if original.interpretation_confidence is not None:
            edited["interpretation_confidence"] = float(original.interpretation_confidence)
        if issues := forbidden_ops(ops) or validate_schema(edited, "patch"):
            raise PatchRejected(issues)
        row = IrPatch(id=edited["patch_id"], process_id=proc.id, base_version=original.base_version, ops=ops,
                      author_kind="user", author_id=reviewer.id, reason=edited["reason"], evidence=original.evidence,
                      interpretation_confidence=original.interpretation_confidence, auto_apply=True,
                      status="proposed", supersedes_patch_id=original.id, changed_paths=changed_paths(ops))
        self.s.add(row)
        await self.s.flush()
        result = await self._apply(proc, row, reviewer)
        if result.status == "applied":
            original.status, original.reviewed_by, original.reviewed_at = "superseded", reviewer.id, now
            original.review_reason = reason
            await write_audit(self.s, actor_kind=reviewer.kind, actor_id=reviewer.id, action="patch.superseded",
                              target=original.id, process_id=proc.id, after={"superseded_by": row.id})
        return result

    async def reject(self, patch_id: str, *, reviewer: Actor, reason: str) -> IrPatch:
        if not reason or not reason.strip():
            raise PatchRejected([Issue("envelope", "/reason", "a reason is required to reject a patch")])
        row = await self.get_patch(patch_id, lock=True)
        if row.status != "proposed":
            raise Conflict("/problems/patch-not-proposed", f"patch {patch_id} is {row.status}",
                           patch_status=row.status)
        row.status, row.reviewed_by, row.reviewed_at, row.review_reason = "rejected", reviewer.id, self.clock(), reason
        await write_audit(self.s, actor_kind=reviewer.kind, actor_id=reviewer.id, action="patch.rejected",
                          target=row.id, process_id=row.process_id, after={"reason": reason})
        await self.s.flush()
        return row

    async def revert(self, patch_id: str, *, actor: Actor, reason: str | None = None) -> PatchResult:
        """Undo an applied patch with its inverse, as a new patch (history is never rewritten).

        Conflicts (409) when a later patch changed the same paths: undo that one first.
        """
        original = await self.get_patch(patch_id)
        if original.status != "applied":
            raise Conflict("/problems/patch-not-applied", f"patch {patch_id} is {original.status}",
                           patch_status=original.status)
        before = await self.s.get(IrVersion, (original.process_id, original.applied_version - 1))
        after = await self.s.get(IrVersion, (original.process_id, original.applied_version))
        ops = jsonpatch.make_patch(content_view(after.snapshot), content_view(before.snapshot)).patch
        if not ops:
            raise Conflict("/problems/nothing-to-undo", f"patch {patch_id} changed nothing")
        result = await self.submit({
            "patch_id": f"undo_{patch_id}"[:60] + f"_{uuid7_str()[-8:]}", "process_id": original.process_id,
            "base_version": original.applied_version, "ops": ops, "author": {"kind": "user", "id": actor.id},
            "reason": reason or f"Undo {patch_id}", "auto_apply": True, "status": "proposed"}, actor=actor)
        if result.status == "applied":
            await write_audit(self.s, actor_kind=actor.kind, actor_id=actor.id, action="patch.reverted",
                              target=patch_id, process_id=original.process_id, after={"by_patch": result.patch_id})
        return result

    # ------------------------------------------------------------------ fork (M11)
    async def fork(self, as_is_id: str, *, actor: Actor, to_process_id: str | None = None,
                   name: str | None = None, description: str | None = None) -> ForkResult:
        """Copy a confirmed as-is into a new to-be at v0 with derived_from set, and freeze the as-is."""
        proc = await self.get_process(as_is_id, lock=True)
        if proc.variant != "as_is":
            raise Conflict("/problems/not-an-as-is", f"{as_is_id} is a {proc.variant}, only an as-is can be forked")
        if proc.frozen_at is not None:
            raise Conflict("/problems/already-forked", f"{as_is_id} has already been forked")
        as_is = await self.get_ir(as_is_id)
        unconfirmed = sorted(eid for c in ELEMENT_COLLECTIONS for eid, x in as_is[c].items()
                             if x["meta"]["status"] not in DEAD_STATUSES and x["meta"]["status"] != "confirmed")
        if unconfirmed or not as_is["nodes"]:
            raise Conflict("/problems/as-is-not-confirmed",
                           "every element of the as-is must be confirmed (playback) before forking",
                           unconfirmed=unconfirmed)

        overrides = {"id": to_process_id or to_be_id_for(as_is_id), "name": name or as_is["process"]["name"],
                     "variant": "to_be", "derived_from": {"process_id": as_is_id, "version": proc.current_version},
                     "version": 0, "status": "draft"}
        if description or as_is["process"].get("description"):
            overrides["description"] = description or as_is["process"]["description"]
        to_be = copy.deepcopy(as_is)
        to_be.pop("stories", None)  # derived; M7 renders the to-be's own
        to_be["process"].update(overrides)
        to_be["process"]["updated_at"] = iso(self.clock())
        await self._insert_process(to_be, actor, action="process.created")

        proc.frozen_at = self.clock()
        if proc.idea_id:
            idea = await self.s.get(Idea, proc.idea_id, with_for_update=True)
            idea.to_be_process_id = overrides["id"]
            idea.as_is_process_id = idea.as_is_process_id or as_is_id
        fork = {"from_process_id": as_is_id, "from_version": proc.current_version, "to_process_id": overrides["id"],
                "process_overrides": overrides}
        await write_audit(self.s, actor_kind=actor.kind, actor_id=actor.id, action="process.forked",
                          target=as_is_id, process_id=as_is_id, after=fork)
        await self.s.flush()
        return ForkResult(as_is_id, overrides["id"], fork)

    # ------------------------------------------------------------------ internals
    def _check_not_frozen(self, proc: Process) -> None:
        if proc.frozen_at is not None:
            raise Conflict("/problems/process-frozen",
                           f"{proc.id} is a forked as-is and is read-only; change the to-be instead")

    def _validate(self, ir: dict) -> None:
        if issues := validate_schema(ir) or validate_integrity(ir):
            raise PatchRejected(issues)

    @staticmethod
    def _envelope(row: IrPatch) -> dict:
        env = {"patch_id": row.id, "process_id": row.process_id, "base_version": row.base_version, "ops": row.ops,
               "author": {"kind": row.author_kind, "id": row.author_id}, "reason": row.reason,
               "auto_apply": row.auto_apply, "status": "proposed"}
        if row.evidence:
            env["evidence"] = row.evidence
        return env

    def _dry_run(self, current: dict, row: IrPatch) -> dict:
        doc = apply_patch(current, self._envelope(row))
        if (row.evidence or {}).get("answer_id") and not answer_confirmations(current, doc, row.ops):
            raise PatchRejected([Issue("envelope", "/evidence/answer_id",
                                       "a patch from an SME answer must confirm the element(s) it answers "
                                       "(meta.status = confirmed with confirmed_by)")])
        return doc

    async def _conflicts(self, proc: Process, row: IrPatch) -> list[str]:
        """Path-level rebase: a stale patch applies unless it touches a path changed since its base version."""
        if row.base_version >= proc.current_version:
            return []
        q = select(IrPatch.changed_paths).where(IrPatch.process_id == proc.id, IrPatch.status == "applied",
                                                IrPatch.applied_version > row.base_version,
                                                IrPatch.applied_version <= proc.current_version)
        touched = [p for paths in (await self.s.execute(q)).scalars() for p in paths]
        return conflicting_paths(row.ops, touched)

    async def _mark_conflicted(self, proc: Process, row: IrPatch, conflicts: list[str]) -> PatchResult:
        row.status = "conflicted"
        self.s.add(row)
        await write_audit(self.s, actor_kind=row.author_kind, actor_id=row.author_id, action="patch.conflicted",
                          target=row.id, process_id=proc.id, after={"conflicting_paths": conflicts})
        await self.s.flush()
        return self._result(row, proc, conflicting=conflicts)

    async def _apply(self, proc: Process, row: IrPatch, actor: Actor) -> PatchResult:
        if conflicts := await self._conflicts(proc, row):
            return await self._mark_conflicted(proc, row, conflicts)
        current = await self.get_ir(proc.id)
        doc = self._dry_run(current, row)
        score_elements(doc)
        frm, to = proc.current_version, proc.current_version + 1
        if doc["process"]["status"] == "exported":  # docs/01 §4: a new patch after export re-opens review
            doc["process"]["status"] = "in_review"
        doc["process"]["version"], doc["process"]["updated_at"] = to, iso(self.clock())

        self.s.add(IrVersion(process_id=proc.id, version=to, snapshot=doc, ir_hash=ir_hash(doc), patch_id=row.id))
        proc.current_version = to
        proc.name, proc.status = doc["process"]["name"], doc["process"]["status"]
        proc.domain, proc.description = doc["process"].get("domain"), doc["process"].get("description")
        row.status, row.applied_version, row.changed_paths = "applied", to, changed_paths(row.ops)
        await write_audit(self.s, actor_kind=actor.kind, actor_id=actor.id, action="patch.applied", target=row.id,
                          process_id=proc.id, before={"version": frm},
                          after={"version": to, "changed_paths": row.changed_paths})
        await enqueue_event(self.s, self._event("ir.patched", proc, to, {
            "patch_id": row.id, "from_version": frm, "to_version": to, "changed_paths": row.changed_paths}))
        await self.s.flush()
        return self._result(row, proc)

    def _event(self, type_: str, proc: Process, version: int | None, payload: dict) -> EventEnvelope:
        return EventEnvelope(type=type_, process_id=proc.id, ir_version=version, correlation_id=self.correlation_id,
                             payload=payload)

    @staticmethod
    def _result(row: IrPatch, proc: Process, conflicting: list[str] | None = None) -> PatchResult:
        return PatchResult(patch_id=row.id, status=row.status, process_id=proc.id, base_version=row.base_version,
                           current_version=proc.current_version, to_version=row.applied_version,
                           changed_paths=list(row.changed_paths or []), conflicting_paths=conflicting or [])
