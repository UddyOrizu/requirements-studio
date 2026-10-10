"""RFC 7807 problem+json responses (docs/03)."""
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ir_core import PatchRejected
from services.common.errors import Forbidden, InvalidInput
from services.ir_store.service import Conflict, NotFound
from services.llm_gateway import CassetteMissing, LLMOutputInvalid, ProviderError

MEDIA_TYPE = "application/problem+json"


def problem(status: int, type_: str, title: str, **extra: Any) -> JSONResponse:
    return JSONResponse({"type": type_, "title": title, "status": status, **extra}, status_code=status,
                        media_type=MEDIA_TYPE)


def register(app: FastAPI) -> None:
    @app.exception_handler(PatchRejected)
    async def _invalid(request: Request, exc: PatchRejected) -> JSONResponse:
        return problem(422, "/problems/patch-invalid", "The patch would produce an invalid IR",
                       errors=[asdict(e) for e in exc.errors])

    @app.exception_handler(CassetteMissing)
    @app.exception_handler(LLMOutputInvalid)
    @app.exception_handler(ProviderError)
    async def _llm(request: Request, exc: Exception) -> JSONResponse:
        # Nothing was recorded (the request's transaction rolls back); the user can retry the same answer.
        return problem(503, "/problems/llm-unavailable", "The assistant could not process that just now",
                       detail=str(exc)[:500])

    @app.exception_handler(NotFound)
    async def _not_found(request: Request, exc: NotFound) -> JSONResponse:
        return problem(404, "/problems/not-found", str(exc))

    @app.exception_handler(Conflict)
    async def _conflict(request: Request, exc: Conflict) -> JSONResponse:
        return problem(409, exc.problem, exc.title, **exc.extra)

    @app.exception_handler(InvalidInput)
    async def _input(request: Request, exc: InvalidInput) -> JSONResponse:
        return problem(422, "/problems/invalid-input", exc.message, errors=[{"path": exc.path,
                                                                              "message": exc.message}])

    @app.exception_handler(Forbidden)
    async def _forbidden(request: Request, exc: Forbidden) -> JSONResponse:
        return problem(403, "/problems/forbidden", str(exc))
