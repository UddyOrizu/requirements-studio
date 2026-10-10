"""M3 REST endpoints (docs/03 §1) plus the M11 fork. Mounted under /api/v1."""
from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from apps.api.deps import CorrelationId, CurrentUser, Session
from apps.api.problems import problem
from services.approvals.service import ApprovalService
from services.identity_audit.auth import Principal

from .db import IrPatch, Process
from .service import Actor, PatchResult, PatchService

router = APIRouter(tags=["processes (M3)"])


class CreateProcess(BaseModel):
    name: str = Field(min_length=1)
    owner_user_id: str
    domain: str | None = None
    description: str | None = None
    variant: Literal["as_is", "to_be"] = "as_is"
    idea_id: str | None = None
    process_id: str | None = Field(None, pattern=r"^proc_[a-z0-9_]{1,60}$")


class AcceptBody(BaseModel):
    ops: list[dict[str, Any]] | None = Field(None, description="Edit-and-accept: replacement ops")
    reason: str | None = None


class RejectBody(BaseModel):
    reason: str = Field(min_length=1)


class ForkBody(BaseModel):
    to_process_id: str | None = Field(None, pattern=r"^proc_[a-z0-9_]{1,60}$")
    name: str | None = None
    description: str | None = None


def _svc(session, cid: str) -> PatchService:
    return PatchService(session, correlation_id=cid)


def _actor(user: Principal) -> Actor:
    return Actor("user", user.user_id)


def _summary(p: Process) -> dict:
    return {"id": p.id, "name": p.name, "domain": p.domain, "description": p.description,
            "owner_user_id": p.owner_user_id, "status": p.status, "variant": p.variant, "idea_id": p.idea_id,
            "current_version": p.current_version, "frozen": p.frozen_at is not None}


def _patch(row: IrPatch) -> dict:
    return {"patch_id": row.id, "process_id": row.process_id, "base_version": row.base_version,
            "applied_version": row.applied_version, "ops": row.ops,
            "author": {"kind": row.author_kind, "id": row.author_id}, "reason": row.reason, "evidence": row.evidence,
            "interpretation_confidence": None if row.interpretation_confidence is None
            else float(row.interpretation_confidence),
            "auto_apply": row.auto_apply, "status": row.status, "reviewed_by": row.reviewed_by,
            "review_reason": row.review_reason, "supersedes_patch_id": row.supersedes_patch_id,
            "changed_paths": row.changed_paths}


def _require_owner_or_admin(user: Principal, proc: Process) -> None:
    if user.user_id != proc.owner_user_id and not user.is_admin:
        raise HTTPException(403, "only the process owner or an admin can do this")


def _approvals(request: Request, session, cid: str) -> ApprovalService:
    return ApprovalService(session, request.app.state.llm, clock=request.app.state.clock, correlation_id=cid,
                           web_base_url=request.app.state.settings.web_base_url)


def _patch_response(r: PatchResult) -> JSONResponse:
    if r.status == "conflicted":
        return problem(409, "/problems/patch-conflict", "Patch conflicts with newer changes", patch_id=r.patch_id,
                       base_version=r.base_version, current_version=r.current_version,
                       conflicting_paths=r.conflicting_paths)
    if r.status == "applied":
        return JSONResponse({"patch_id": r.patch_id, "status": "applied", "to_version": r.to_version,
                             "changed_paths": r.changed_paths}, status_code=201)
    return JSONResponse({"patch_id": r.patch_id, "status": r.status}, status_code=202)


@router.post("/processes", status_code=201)
async def create_process(body: CreateProcess, user: CurrentUser, session: Session, cid: CorrelationId) -> dict:
    if body.owner_user_id != user.user_id and not user.is_admin:
        raise HTTPException(403, "you can create processes you own; an admin can create them for others")
    ir = await _svc(session, cid).create_process(actor=_actor(user), **body.model_dump())
    await session.commit()
    return {"process_id": ir["process"]["id"], "ir": ir}


@router.get("/processes")
async def list_processes(user: CurrentUser, session: Session, cid: CorrelationId,
                         idea_id: str | None = None) -> list[dict]:
    return [_summary(p) for p in await _svc(session, cid).list_processes(idea_id)]


@router.get("/processes/{pid}")
async def get_process(pid: str, user: CurrentUser, session: Session, cid: CorrelationId) -> dict:
    return _summary(await _svc(session, cid).get_process(pid))


@router.get("/processes/{pid}/ir")
async def get_ir(pid: str, user: CurrentUser, session: Session, cid: CorrelationId,
                 version: int | None = Query(None, ge=0)) -> dict:
    return await _svc(session, cid).get_ir(pid, version)


@router.get("/processes/{pid}/ir/diff")
async def diff(pid: str, user: CurrentUser, session: Session, cid: CorrelationId,
               from_: int = Query(alias="from", ge=0), to: int = Query(ge=0)) -> list[dict]:
    return await _svc(session, cid).diff(pid, from_, to)


@router.post("/processes/{pid}/patches")
async def submit_patch(pid: str, patch: dict[str, Any], request: Request, user: CurrentUser, session: Session,
                       cid: CorrelationId,
                       reviewer: str | None = Query(None, description="Who to ask to review it if it is proposed "
                                                                      "(default: the process owner)")) -> JSONResponse:
    svc = _svc(session, cid)
    proc = await svc.get_process(pid)
    _require_owner_or_admin(user, proc)
    if patch.get("process_id") != pid:
        raise HTTPException(422, "patch.process_id does not match the URL")
    # Agents submit through PatchService in-process; over HTTP the author is the signed-in user.
    if patch.get("author") != {"kind": "user", "id": user.user_id}:
        raise HTTPException(403, "author must be {kind: user, id: <your user id>}")
    result = await svc.submit(patch, actor=_actor(user))
    if result.status == "proposed":  # awaits review: email the reviewer an approval request
        assignee = reviewer or proc.owner_user_id
        if assignee != user.user_id:
            await _approvals(request, session, cid).request("patch_review", actor=user, assignee_user_id=assignee,
                                                            subject_id=result.patch_id)
    await session.commit()
    return _patch_response(result)


@router.get("/processes/{pid}/patches")
async def list_patches(pid: str, user: CurrentUser, session: Session, cid: CorrelationId,
                       status: str | None = None) -> list[dict]:
    return [_patch(p) for p in await _svc(session, cid).list_patches(pid, status)]


@router.post("/patches/{patch_id}/accept")
async def accept_patch(patch_id: str, request: Request, user: CurrentUser, session: Session, cid: CorrelationId,
                       body: AcceptBody | None = None) -> JSONResponse:
    svc = _svc(session, cid)
    row = await svc.get_patch(patch_id)
    _require_owner_or_admin(user, await svc.get_process(row.process_id))
    body = body or AcceptBody()
    result = await svc.accept(patch_id, reviewer=_actor(user), ops=body.ops, reason=body.reason)
    if result.status == "applied":
        await _approvals(request, session, cid).settle("patch_review", patch_id, by=user.user_id)
    await session.commit()
    return _patch_response(result)


@router.post("/patches/{patch_id}/reject")
async def reject_patch(patch_id: str, body: RejectBody, request: Request, user: CurrentUser, session: Session,
                       cid: CorrelationId) -> dict:
    svc = _svc(session, cid)
    row = await svc.get_patch(patch_id)
    _require_owner_or_admin(user, await svc.get_process(row.process_id))
    row = await svc.reject(patch_id, reviewer=_actor(user), reason=body.reason)
    await _approvals(request, session, cid).settle("patch_review", patch_id, by=user.user_id)
    await session.commit()
    return _patch(row)


@router.post("/processes/{pid}/fork", status_code=201)
async def fork(pid: str, user: CurrentUser, session: Session, cid: CorrelationId,
               body: ForkBody | None = None) -> dict:
    svc = _svc(session, cid)
    _require_owner_or_admin(user, await svc.get_process(pid))
    result = await svc.fork(pid, actor=_actor(user), **(body or ForkBody()).model_dump())
    await session.commit()
    return asdict(result)
