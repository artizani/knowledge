"""FastAPI application: routes, error contract, and request logging.

Built via a ``create_app`` factory so tests can construct isolated instances
and override the ``get_session`` dependency. The same app object is wrapped by
Mangum in :mod:`handler` for AWS Lambda + API Gateway.
"""
from __future__ import annotations

import time
import uuid

from fastapi import Depends, FastAPI, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.auth import require_read_auth, require_write_auth
from app.config import get_settings
from app.constants import KNOWLEDGE_STATUSES, KNOWLEDGE_TYPES
from app.database import get_session
from app.errors import AuthError, NotFoundError
from app.logging_config import configure_logging, get_logger
from app.schemas import (
    CaptureRequest,
    CaptureResponse,
    DeleteResponse,
    KnowledgeListResponse,
    KnowledgeOut,
    SearchRequest,
    UpdateRequest,
)
from app.service import KnowledgeService

logger = get_logger()


def get_service(session: Session = Depends(get_session)) -> KnowledgeService:
    return KnowledgeService(session)


def _error(status_code: int, code: str, detail=None, headers=None) -> JSONResponse:
    body: dict = {"error": code}
    if detail is not None:
        body["detail"] = detail
    # jsonable_encoder makes nested pydantic error contexts (which may contain
    # raw exception objects) safe to serialise.
    return JSONResponse(
        status_code=status_code, content=jsonable_encoder(body), headers=headers
    )


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AuthError)
    async def _auth(request: Request, exc: AuthError):
        return _error(401, "unauthorised", headers={"WWW-Authenticate": "Bearer"})

    @app.exception_handler(NotFoundError)
    async def _not_found(request: Request, exc: NotFoundError):
        return _error(404, "not_found", "Knowledge not found")

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        return _error(400, "invalid_payload", exc.errors())

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = {401: "unauthorised", 404: "not_found", 400: "invalid_payload"}.get(
            exc.status_code, "error"
        )
        return _error(exc.status_code, code, exc.detail)


def _add_logging_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id
        request.state.namespace = None
        request.state.endpoint = None

        start = time.perf_counter()
        status_code = 500
        failure = None
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:  # unexpected -> masked 500
            failure = exc
            response = _error(500, "internal_error", "Unexpected server error")
            status_code = 500

        latency_ms = round((time.perf_counter() - start) * 1000, 3)
        endpoint = getattr(request.state, "endpoint", None) or (
            f"{request.method} {request.url.path}"
        )
        log_kwargs = {
            "request_id": request_id,
            "endpoint": endpoint,
            "namespace": getattr(request.state, "namespace", None),
            "latency_ms": latency_ms,
            "status_code": status_code,
            "success": status_code < 400,
        }
        if failure is not None:
            logger.error("request", extra=log_kwargs, exc_info=failure)
        else:
            logger.info("request", extra=log_kwargs)

        response.headers["x-request-id"] = request_id
        return response


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Knowledge API",
        version="1.0.0",
        description="Central knowledge layer for capturing and retrieving product knowledge.",
    )
    _register_error_handlers(app)
    _add_logging_middleware(app)

    # -- meta ------------------------------------------------------------- #
    @app.get("/", tags=["meta"])
    async def root():
        return {
            "service": "knowledge-api",
            "version": "1.0.0",
            "status": "ok",
            "types": list(KNOWLEDGE_TYPES),
            "statuses": list(KNOWLEDGE_STATUSES),
        }

    @app.get("/health", tags=["meta"])
    async def health():
        return {"status": "ok"}

    # -- capture ---------------------------------------------------------- #
    @app.post("/capture", response_model=CaptureResponse, status_code=201, tags=["knowledge"])
    async def capture(
        payload: CaptureRequest,
        request: Request,
        service: KnowledgeService = Depends(get_service),
        _principal=Depends(require_write_auth),
    ):
        request.state.endpoint = "POST /capture"
        request.state.namespace = payload.namespace
        knowledge = service.capture(payload)
        return CaptureResponse(id=knowledge.id, status="captured")

    # -- read one --------------------------------------------------------- #
    @app.get("/knowledge/{knowledge_id}", response_model=KnowledgeOut, tags=["knowledge"])
    async def get_one(
        knowledge_id: uuid.UUID,
        request: Request,
        service: KnowledgeService = Depends(get_service),
        _principal=Depends(require_read_auth),
    ):
        request.state.endpoint = "GET /knowledge/{id}"
        knowledge = service.get(knowledge_id)
        request.state.namespace = knowledge.namespace
        return KnowledgeOut.model_validate(knowledge)

    # -- list ------------------------------------------------------------- #
    @app.get("/knowledge", response_model=KnowledgeListResponse, tags=["knowledge"])
    async def list_knowledge(
        request: Request,
        namespace: str | None = Query(default=None),
        type: str | None = Query(default=None),
        status: str | None = Query(default=None),
        limit: int | None = Query(default=None, ge=1, le=1000),
        service: KnowledgeService = Depends(get_service),
        _principal=Depends(require_read_auth),
    ):
        request.state.endpoint = "GET /knowledge"
        request.state.namespace = namespace
        items = service.list(
            namespace=namespace, type=type, status=status, limit=limit
        )
        return KnowledgeListResponse(
            items=[KnowledgeOut.model_validate(k) for k in items], count=len(items)
        )

    # -- search ----------------------------------------------------------- #
    @app.post("/search", response_model=KnowledgeListResponse, tags=["knowledge"])
    async def search(
        payload: SearchRequest,
        request: Request,
        service: KnowledgeService = Depends(get_service),
        _principal=Depends(require_read_auth),
    ):
        request.state.endpoint = "POST /search"
        request.state.namespace = payload.namespace
        items = service.search(payload)
        return KnowledgeListResponse(
            items=[KnowledgeOut.model_validate(k) for k in items], count=len(items)
        )

    # -- update ----------------------------------------------------------- #
    @app.put("/knowledge/{knowledge_id}", response_model=KnowledgeOut, tags=["knowledge"])
    async def update(
        knowledge_id: uuid.UUID,
        payload: UpdateRequest,
        request: Request,
        service: KnowledgeService = Depends(get_service),
        _principal=Depends(require_write_auth),
    ):
        request.state.endpoint = "PUT /knowledge/{id}"
        knowledge = service.update(knowledge_id, payload)
        request.state.namespace = knowledge.namespace
        return KnowledgeOut.model_validate(knowledge)

    # -- delete ----------------------------------------------------------- #
    @app.delete("/knowledge/{knowledge_id}", response_model=DeleteResponse, tags=["knowledge"])
    async def delete(
        knowledge_id: uuid.UUID,
        request: Request,
        service: KnowledgeService = Depends(get_service),
        _principal=Depends(require_write_auth),
    ):
        request.state.endpoint = "DELETE /knowledge/{id}"
        knowledge = service.delete(knowledge_id)
        request.state.namespace = knowledge.namespace
        return DeleteResponse(id=knowledge.id, status="deleted")

    return app
