"""M0 REST endpoints (docs/modules/M0 §5). The WebSocket stream arrives with the conversation UI."""
from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from apps.api.deps import CorrelationId, CurrentUser, Session
from services.identity_audit.auth import Principal

from .db import IntakeSession
from .service import IntakeService, TurnResult

router = APIRouter(tags=["intake (M0)"])
STAFF_ROLES = {"ba", "admin"}


class StartBody(BaseModel):
    idea_text: str = Field(min_length=1)
    has_process_today: Literal["yes", "no", "not_sure"]
    title: str | None = None
    description: str | None = None
    domain: str | None = None
    idea_id: str | None = Field(None, pattern=r"^idea_[a-z0-9_]{1,60}$")


class AnswerBody(BaseModel):
    text: str | None = None
    choice: str | None = Field(None, description="A suggested answer the requester clicked")
    special: Literal["not_sure_ask", "skip"] | None = None
    ask_sme_id: str | None = None


class JumpBody(BaseModel):
    phase: Literal["validate"]


def _service(request: Request, session, cid: str) -> IntakeService:
    return IntakeService(session, request.app.state.llm, clock=request.app.state.clock, correlation_id=cid)


async def _authorised(svc: IntakeService, session_id: str, user: Principal) -> IntakeSession:
    sess = await svc._session(session_id)
    if user.user_id != sess.requester_user_id and not STAFF_ROLES & set(user.roles):
        raise HTTPException(403, "only the requester (or a BA) can work in this session")
    return sess


def _turn(result: TurnResult) -> dict:
    return asdict(result)


@router.post("/intake-sessions", status_code=201)
async def start(body: StartBody, request: Request, user: CurrentUser, session: Session, cid: CorrelationId) -> dict:
    svc = _service(request, session, cid)
    result = await svc.start(idea_text=body.idea_text, has_process_today=body.has_process_today,
                             requester_id=user.user_id, requester_name=user.name or user.user_id, title=body.title,
                             description=body.description, domain=body.domain, idea_id=body.idea_id)
    await session.commit()
    return _turn(result)


@router.get("/intake-sessions/{session_id}")
async def get_session(session_id: str, request: Request, user: CurrentUser, session: Session,
                      cid: CorrelationId) -> dict:
    svc = _service(request, session, cid)
    sess = await _authorised(svc, session_id, user)
    pending = await svc._pending_turn(sess)
    return {**await svc.export(session_id), "coverage": sess.coverage,
            "next_question": asdict(svc._as_question(pending)) if pending else None}


@router.post("/intake-sessions/{session_id}/answers")
async def answer(session_id: str, body: AnswerBody, request: Request, user: CurrentUser, session: Session,
                 cid: CorrelationId) -> dict:
    svc = _service(request, session, cid)
    await _authorised(svc, session_id, user)
    result = await svc.answer(session_id, text=body.text or body.choice, special=body.special,
                              ask_sme_id=body.ask_sme_id)
    await session.commit()
    return _turn(result)


@router.post("/intake-sessions/{session_id}/turns/{n}/undo")
async def undo(session_id: str, n: int, request: Request, user: CurrentUser, session: Session,
               cid: CorrelationId) -> dict:
    svc = _service(request, session, cid)
    await _authorised(svc, session_id, user)
    result = await svc.undo(session_id, n)
    await session.commit()
    return _turn(result)


@router.post("/intake-sessions/{session_id}/jump")
async def jump(session_id: str, body: JumpBody, request: Request, user: CurrentUser, session: Session,
               cid: CorrelationId) -> dict:
    svc = _service(request, session, cid)
    await _authorised(svc, session_id, user)
    result = await svc.jump(session_id, body.phase)
    await session.commit()
    return _turn(result)


@router.post("/intake-sessions/{session_id}/signoff")
async def sign_off(session_id: str, request: Request, user: CurrentUser, session: Session,
                   cid: CorrelationId) -> dict:
    svc = _service(request, session, cid)
    sess = await _authorised(svc, session_id, user)
    if user.user_id != sess.requester_user_id:
        raise HTTPException(403, "only the requester (the process owner) signs off")
    result = await svc.sign_off(session_id, user_id=user.user_id)
    await session.commit()
    return _turn(result)
