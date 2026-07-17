"""RFC-7807-style error envelope and exception handlers.

Every error response is `{code, message, detail}` (01-architecture §4) so the
web client has one shape to parse.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class APIError(Exception):
    """Domain error carrying a stable machine code and HTTP status."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        detail: object | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail


def _envelope(code: str, message: str, detail: object | None = None) -> dict:
    return {"code": code, "message": message, "detail": detail}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def _handle_api_error(_: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.detail),
        )

    @app.exception_handler(HTTPException)
    async def _handle_http_error(_: Request, exc: HTTPException) -> JSONResponse:
        code = exc.detail if isinstance(exc.detail, str) else "http_error"
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(code, str(exc.detail)),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_envelope(
                "validation_error",
                "Request validation failed",
                jsonable_encoder(exc.errors()),
            ),
        )
