"""M12 REST endpoints. Stories and patches are addressed through their idea: story ids repeat across processes
(an as-is and its to-be share them), so docs/03's /stories/{sid}/… paths become /ideas/{id}/stories/{sid}/…."""
from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field

from apps.api.deps import CorrelationId, CurrentUser, Session
from services.identity_audit.auth import Principal
from services.intake.service import IntakeService

from .refine import RefinementService
from .service import IdeasService

router = APIRouter(tags=["ideas (M12)"])


class NewIdea(BaseModel):
    text: str = Field(min_length=1)
    has_process_today: Literal["yes", "no", "not_sure"]
    title: str | None = None


class RefineBody(BaseModel):
    instruction: str = Field(min_length=1, max_length=2000)


class EditBody(BaseModel):
    field: Literal["priority", "outcome", "control_mode", "acceptance_criterion"]
    value: Any
    ac_id: str | None = None
    part: Literal["title", "given", "when", "then"] | None = None


class AskBody(BaseModel):
    text: str = Field(min_length=1, max_length=400)
    user_id: str | None = Field(None, description="The person to ask (emailed the question)")
    sme_id: str | None = Field(None, description="An SME directory entry instead of a user")


def _ideas(request: Request, session, cid: str) -> IdeasService:
    return IdeasService(session, request.app.state.llm, clock=request.app.state.clock, correlation_id=cid)


async def _can_change(svc: IdeasService, idea_id: str, user: Principal) -> None:
    idea = await svc.idea(idea_id)
    if user.user_id != idea.owner_user_id and not user.is_admin:
        raise HTTPException(403, "only the idea's owner (or an admin) can change it")


@router.get("/ideas")
async def list_ideas(request: Request, user: CurrentUser, session: Session, cid: CorrelationId,
                     status: str | None = None, owner: str | None = None, q: str | None = None,
                     tag: str | None = None) -> list[dict]:
    return await _ideas(request, session, cid).list_ideas(status=status, owner=owner, q=q, tag=tag)


@router.post("/ideas", status_code=201)
async def new_idea(body: NewIdea, request: Request, user: CurrentUser, session: Session, cid: CorrelationId) -> dict:
    """Idea + session + first question (M12 New idea → M0)."""
    intake = IntakeService(session, request.app.state.llm, clock=request.app.state.clock, correlation_id=cid)
    result = await intake.start(idea_text=body.text, has_process_today=body.has_process_today,
                                requester_id=user.user_id, requester_name=user.name or user.user_id, title=body.title)
    sess = await intake._session(result.session_id)
    await session.commit()
    return {"idea_id": sess.idea_id, "session_id": sess.id, "turn": asdict(result)}


@router.get("/ideas/{idea_id}")
async def get_idea(idea_id: str, request: Request, user: CurrentUser, session: Session, cid: CorrelationId) -> dict:
    return await _ideas(request, session, cid).overview(idea_id)


@router.get("/ideas/{idea_id}/flow")
async def flow(idea_id: str, request: Request, user: CurrentUser, session: Session, cid: CorrelationId,
               variant: Literal["as_is", "to_be"] | None = None,
               format: Literal["json", "drawio", "mermaid"] = "json"):  # noqa: A002 (docs/03 parameter name)
    body = await _ideas(request, session, cid).flow(idea_id, variant, format)
    if format == "drawio":
        return Response(body, media_type="application/vnd.jgraph.mxfile", headers={
            "Content-Disposition": f'attachment; filename="{variant or "process"}_process_flow.drawio"'})
    if format == "mermaid":
        return Response(body, media_type="text/vnd.mermaid")
    return body


@router.get("/ideas/{idea_id}/flow/compare")
async def compare(idea_id: str, request: Request, user: CurrentUser, session: Session, cid: CorrelationId) -> dict:
    return await _ideas(request, session, cid).compare(idea_id)


@router.get("/ideas/{idea_id}/stories")
async def stories(idea_id: str, request: Request, user: CurrentUser, session: Session,
                  cid: CorrelationId) -> list[dict]:
    return await _ideas(request, session, cid).stories(idea_id)


@router.get("/ideas/{idea_id}/stories.md", response_class=PlainTextResponse)
async def stories_md(idea_id: str, request: Request, user: CurrentUser, session: Session, cid: CorrelationId) -> str:
    return await _ideas(request, session, cid).stories_markdown(idea_id)


@router.get("/ideas/{idea_id}/features", response_class=PlainTextResponse)
async def features(idea_id: str, request: Request, user: CurrentUser, session: Session, cid: CorrelationId) -> str:
    return await _ideas(request, session, cid).feature(idea_id)


@router.get("/ideas/{idea_id}/stories/{sid}")
async def story(idea_id: str, sid: str, request: Request, user: CurrentUser, session: Session,
                cid: CorrelationId) -> dict:
    return await _ideas(request, session, cid).story(idea_id, sid)


@router.get("/ideas/{idea_id}/stories/{sid}/history")
async def history(idea_id: str, sid: str, request: Request, user: CurrentUser, session: Session,
                  cid: CorrelationId) -> list[dict]:
    return await _ideas(request, session, cid).history(idea_id, sid)


@router.post("/ideas/{idea_id}/stories/{sid}/refine")
async def refine(idea_id: str, sid: str, body: RefineBody, request: Request, user: CurrentUser, session: Session,
                 cid: CorrelationId) -> dict:
    svc = RefinementService(session, request.app.state.llm, clock=request.app.state.clock, correlation_id=cid)
    await _can_change(svc.ideas, idea_id, user)
    result = await svc.preview(idea_id, sid, instruction=body.instruction, user_id=user.user_id)
    await session.commit()
    return result


@router.post("/ideas/{idea_id}/stories/{sid}/refine/{preview_id}/apply")
async def apply_refinement(idea_id: str, sid: str, preview_id: str, request: Request, user: CurrentUser,
                           session: Session, cid: CorrelationId) -> dict:
    svc = RefinementService(session, request.app.state.llm, clock=request.app.state.clock, correlation_id=cid)
    await _can_change(svc.ideas, idea_id, user)
    result = await svc.apply(idea_id, sid, preview_id, user_id=user.user_id)
    await session.commit()
    return result


@router.post("/ideas/{idea_id}/stories/{sid}/edit")
async def edit(idea_id: str, sid: str, body: EditBody, request: Request, user: CurrentUser, session: Session,
               cid: CorrelationId) -> dict:
    svc = _ideas(request, session, cid)
    await _can_change(svc, idea_id, user)
    result = await svc.edit(idea_id, sid, user_id=user.user_id, field=body.field, value=body.value,
                            ac_id=body.ac_id, part=body.part)
    await session.commit()
    return result


@router.post("/ideas/{idea_id}/stories/{sid}/ask")
async def ask(idea_id: str, sid: str, body: AskBody, request: Request, user: CurrentUser, session: Session,
              cid: CorrelationId) -> dict:
    svc = _ideas(request, session, cid)
    await _can_change(svc, idea_id, user)
    result = await svc.ask(idea_id, sid, user_id=user.user_id, text=body.text, sme_id=body.sme_id,
                           ask_user_id=body.user_id)
    await session.commit()
    return result


@router.post("/ideas/{idea_id}/patches/{patch_id}/undo")
async def undo(idea_id: str, patch_id: str, request: Request, user: CurrentUser, session: Session,
               cid: CorrelationId) -> dict:
    svc = _ideas(request, session, cid)
    await _can_change(svc, idea_id, user)
    result = await svc.undo(idea_id, patch_id, user_id=user.user_id)
    await session.commit()
    if result["status"] == "conflicted":
        raise HTTPException(409, {"title": "A later change touched the same elements; undo that one first",
                                  "conflicting_paths": result["conflicting_paths"]})
    return result


@router.get("/smes")
async def smes(request: Request, user: CurrentUser, session: Session, cid: CorrelationId) -> list[dict]:
    return await _ideas(request, session, cid).smes()


dev_router = APIRouter(tags=["dev"])


class SeedBody(BaseModel):
    scenario: Literal["samples", "kyc_before_refinement"] = "samples"


@dev_router.post("/dev/seed")
async def seed(body: SeedBody, request: Request, session: Session) -> dict:
    """Dev/test only (not mounted in prod): reset the database to a sample scenario."""
    from .seed import seed as run
    await run(session, body.scenario)
    await session.commit()
    return {"scenario": body.scenario}

