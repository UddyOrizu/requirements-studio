"""M11 REST endpoints. Suggestion ids (S01…) are unique per idea, so decision paths include the idea id."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from apps.api.deps import CorrelationId, CurrentUser, Session
from services.identity_audit.auth import Principal

from .service import ImproveService

router = APIRouter(tags=["improve (M11)"])


class RejectBody(BaseModel):
    reason: str = Field(min_length=1, max_length=300)


class EditBody(BaseModel):
    instruction: str = Field(min_length=1)


def _service(request: Request, session, cid: str) -> ImproveService:
    return ImproveService(session, request.app.state.llm, clock=request.app.state.clock, correlation_id=cid)


async def _owner(svc: ImproveService, idea_id: str, user: Principal):
    idea = await svc._idea(idea_id)
    if user.user_id != idea.owner_user_id and not {"ba", "admin"} & set(user.roles):
        raise HTTPException(403, "only the requester (or a BA) decides suggestions")
    return idea


@router.post("/ideas/{idea_id}/suggestions:generate")
async def generate(idea_id: str, request: Request, user: CurrentUser, session: Session, cid: CorrelationId) -> dict:
    svc = _service(request, session, cid)
    await _owner(svc, idea_id, user)
    result = await svc.generate(idea_id, requester_name=user.name)
    await session.commit()
    return {"suggestions": result.suggestions, "not_suggested": result.not_suggested}


@router.get("/ideas/{idea_id}/suggestions")
async def list_suggestions(idea_id: str, request: Request, user: CurrentUser, session: Session,
                           cid: CorrelationId) -> list[dict]:
    return await _service(request, session, cid).list_suggestions(idea_id)


@router.post("/ideas/{idea_id}/suggestions/{sid}/accept")
async def accept(idea_id: str, sid: str, request: Request, user: CurrentUser, session: Session,
                 cid: CorrelationId) -> dict:
    svc = _service(request, session, cid)
    await _owner(svc, idea_id, user)
    result = await svc.accept(idea_id, sid, user_id=user.user_id)
    await session.commit()
    return result


@router.post("/ideas/{idea_id}/suggestions/{sid}/reject")
async def reject(idea_id: str, sid: str, body: RejectBody, request: Request, user: CurrentUser, session: Session,
                 cid: CorrelationId) -> dict:
    svc = _service(request, session, cid)
    await _owner(svc, idea_id, user)
    result = await svc.reject(idea_id, sid, user_id=user.user_id, reason=body.reason)
    await session.commit()
    return result


@router.post("/ideas/{idea_id}/suggestions/{sid}/edit")
async def edit(idea_id: str, sid: str, body: EditBody, request: Request, user: CurrentUser, session: Session,
               cid: CorrelationId) -> dict:
    svc = _service(request, session, cid)
    await _owner(svc, idea_id, user)
    result = await svc.edit(idea_id, sid, user_id=user.user_id, instruction=body.instruction)
    await session.commit()
    return result


@router.post("/ideas/{idea_id}/suggestions:accept-remaining")
async def accept_remaining(idea_id: str, request: Request, user: CurrentUser, session: Session,
                           cid: CorrelationId) -> list[dict]:
    svc = _service(request, session, cid)
    await _owner(svc, idea_id, user)
    result = await svc.accept_remaining(idea_id, user_id=user.user_id)
    await session.commit()
    return result


@router.get("/ideas/{idea_id}/improvements.md", response_class=PlainTextResponse)
async def report(idea_id: str, request: Request, user: CurrentUser, session: Session, cid: CorrelationId) -> str:
    return await _service(request, session, cid).report(idea_id)
