"""Approval requests (docs/03 §1 Approvals). Mounted under /api/v1."""
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from apps.api.deps import CorrelationId, CurrentUser, Session

from .service import ApprovalService

router = APIRouter(tags=["approvals"])


class NewApproval(BaseModel):
    kind: Literal["patch_review", "story_signoff", "suggestion"]
    assignee_user_id: str
    subject_id: str = Field(min_length=1, description="patch id · intake session id · suggestion id (S01…)")
    idea_id: str | None = Field(None, description="Required for a suggestion")
    message: str | None = Field(None, max_length=1000)


class Decision(BaseModel):
    decision: Literal["approve", "reject", "answer"]
    note: str | None = Field(None, max_length=2000, description="Required to reject; the answer for a question")


def _service(request: Request, session, cid: str) -> ApprovalService:
    return ApprovalService(session, request.app.state.llm, clock=request.app.state.clock, correlation_id=cid,
                           web_base_url=request.app.state.settings.web_base_url)


@router.post("/approvals", status_code=201)
async def create(body: NewApproval, request: Request, user: CurrentUser, session: Session,
                 cid: CorrelationId) -> dict:
    svc = _service(request, session, cid)
    row = await svc.request(body.kind, actor=user, assignee_user_id=body.assignee_user_id,
                            subject_id=body.subject_id, idea_id=body.idea_id, message=body.message)
    await session.commit()
    return await svc.detail(row.id, user)


@router.get("/approvals")
async def list_approvals(request: Request, user: CurrentUser, session: Session, cid: CorrelationId,
                         box: Literal["inbox", "sent", "all"] = "inbox",
                         status: Literal["pending", "approved", "rejected", "answered", "cancelled", "closed",
                                         "any"] = "pending",
                         idea_id: str | None = None) -> list[dict]:
    return await _service(request, session, cid).inbox(user, box=box, status=None if status == "any" else status,
                                                      idea_id=idea_id)


@router.get("/approvals/summary")
async def summary(request: Request, user: CurrentUser, session: Session, cid: CorrelationId) -> dict:
    return await _service(request, session, cid).counts(user)


@router.get("/approvals/{approval_id}")
async def detail(approval_id: str, request: Request, user: CurrentUser, session: Session, cid: CorrelationId) -> dict:
    return await _service(request, session, cid).detail(approval_id, user)


@router.post("/approvals/{approval_id}/decision")
async def decide(approval_id: str, body: Decision, request: Request, user: CurrentUser, session: Session,
                 cid: CorrelationId) -> dict:
    svc = _service(request, session, cid)
    await svc.decide(approval_id, actor=user, decision=body.decision, note=body.note)
    await session.commit()
    return await svc.detail(approval_id, user)


@router.post("/approvals/{approval_id}/cancel")
async def cancel(approval_id: str, request: Request, user: CurrentUser, session: Session, cid: CorrelationId) -> dict:
    svc = _service(request, session, cid)
    await svc.cancel(approval_id, actor=user)
    await session.commit()
    return await svc.detail(approval_id, user)
