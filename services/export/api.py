"""M9 REST endpoints for file exports (docs/modules/M9 API). The MOTHER package endpoints arrive in P9."""
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from apps.api.deps import CorrelationId, CurrentUser, Session

from .service import FORMAT_IDS, ExportService

router = APIRouter(tags=["export (M9)"])


class ExportBody(BaseModel):
    formats: list[str] = Field(min_length=1)
    variant: Literal["to_be", "as_is"] | None = None


def _service(request: Request, session, cid: str) -> ExportService:
    return ExportService(session, request.app.state.settings, request.app.state.export_store,
                         clock=request.app.state.clock, correlation_id=cid)


@router.get("/ideas/{idea_id}/exports/formats")
async def formats(idea_id: str, request: Request, user: CurrentUser, session: Session, cid: CorrelationId) -> dict:
    return await _service(request, session, cid).formats(idea_id)


@router.get("/ideas/{idea_id}/exports/preview")
async def preview(idea_id: str, format: str, request: Request, user: CurrentUser, session: Session,  # noqa: A002
                  cid: CorrelationId, variant: Literal["to_be", "as_is"] | None = None) -> dict:
    if format not in FORMAT_IDS:
        raise HTTPException(422, f"format must be one of {FORMAT_IDS}")
    return await _service(request, session, cid).preview(idea_id, format, variant)


@router.post("/ideas/{idea_id}/exports", status_code=201)
async def create(idea_id: str, body: ExportBody, request: Request, user: CurrentUser, session: Session,
                 cid: CorrelationId) -> dict:
    result = await _service(request, session, cid).create(idea_id, body.formats, user_id=user.user_id,
                                                          variant=body.variant)
    await session.commit()
    return result


@router.get("/ideas/{idea_id}/exports")
async def history(idea_id: str, request: Request, user: CurrentUser, session: Session,
                  cid: CorrelationId) -> list[dict]:
    return await _service(request, session, cid).history(idea_id)


@router.get("/exports/{export_id}")
async def get_export(export_id: str, request: Request, user: CurrentUser, session: Session,
                     cid: CorrelationId) -> dict:
    svc = _service(request, session, cid)
    return svc._out(await svc.get(export_id))


@router.get("/exports/{export_id}/download")
async def download(export_id: str, request: Request, user: CurrentUser, session: Session, cid: CorrelationId,
                   file: str | None = None) -> Response:
    content, filename, content_type = await _service(request, session, cid).download(export_id, file)
    return Response(content, media_type=content_type,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
