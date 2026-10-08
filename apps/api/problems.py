"""RFC 7807 problem+json responses (docs/03)."""
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ir_core import PatchRejected
from services.ir_store.service import Conflict, NotFound

MEDIA_TYPE = "application/problem+json"


def problem(status: int, type_: str, title: str, **extra: Any) -> JSONResponse:
    return JSONResponse({"type": type_, "title": title, "status": status, **extra}, status_code=status,
                        media_type=MEDIA_TYPE)


def register(app: FastAPI) -> None:
    @app.exception_handler(PatchRejected)
    async def _invalid(request: Request, exc: PatchRejected) -> JSONResponse:
        return problem(422, "/problems/patch-invalid", "The patch would produce an invalid IR",
                       errors=[asdict(e) for e in exc.errors])

    @app.exception_handler(NotFound)
    async def _not_found(request: Request, exc: NotFound) -> JSONResponse:
        return problem(404, "/problems/not-found", str(exc))

    @app.exception_handler(Conflict)
    async def _conflict(request: Request, exc: Conflict) -> JSONResponse:
        return problem(409, exc.problem, exc.title, **exc.extra)
