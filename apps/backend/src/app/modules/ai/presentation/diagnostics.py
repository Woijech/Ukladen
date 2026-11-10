from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel

from app.modules.academics.presentation.routes import no_store
from app.modules.ai.application.diagnostics import DiagnosticReview
from app.modules.ai.domain.state import RunStatus
from app.modules.ai.infrastructure.diagnostics import SqlAlchemyDiagnostics
from app.modules.ai.presentation.routes import Ai
from app.modules.ai.presentation.schemas import (
    ConversationCreate,
    ConversationResponse,
    RunResponse,
)
from app.modules.auth.presentation.dependencies import (
    Config,
    CurrentSession,
    get_current_session,
    require_csrf,
)

router = APIRouter(
    prefix="/api/v1/ai/diagnostics",
    tags=["ai-diagnostics"],
    dependencies=[Depends(no_store), Depends(get_current_session)],
)


class DiagnosticAccess(BaseModel):
    allowed: bool
    user_id: UUID


class DiagnosticSummary(BaseModel):
    id: UUID
    conversation_id: UUID | None
    provider: str
    model: str
    status: RunStatus
    created_at: datetime
    finished_at: datetime | None
    credential_source: Literal["demo", "personal", "operator"]
    captured: bool
    verdict: Literal["unreviewed", "passed", "failed"]


class DiagnosticList(BaseModel):
    items: list[DiagnosticSummary]
    has_more: bool


class DiagnosticEvent(BaseModel):
    kind: str
    at: datetime
    payload: dict


class DiagnosticTrace(BaseModel):
    events: list[DiagnosticEvent]
    captured: bool
    truncated: bool
    verdict: Literal["unreviewed", "passed", "failed"]
    note: str


class DiagnosticDetail(BaseModel):
    run: RunResponse
    trace: DiagnosticTrace


def diagnostic_store(
    request: Request, settings: Config, current: CurrentSession
) -> SqlAlchemyDiagnostics:
    if current.user_id not in settings.ai_diagnostic_admin_ids:
        raise HTTPException(403, "AI diagnostics require an operator grant.")
    return SqlAlchemyDiagnostics(request.app.state.session_factory)


Store = Annotated[SqlAlchemyDiagnostics, Depends(diagnostic_store)]


@router.get("/access", response_model=DiagnosticAccess)
def access(settings: Config, current: CurrentSession) -> DiagnosticAccess:
    return DiagnosticAccess(
        allowed=current.user_id in settings.ai_diagnostic_admin_ids, user_id=current.user_id
    )


@router.get("/runs", response_model=DiagnosticList)
def list_runs(
    current: CurrentSession,
    store: Store,
    service: Ai,
    status: RunStatus | None = None,
    days: int = Query(7, ge=1, le=30),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10000),
) -> dict:
    return store.list(current.user_id, status, days, limit, offset)


@router.get("/runs/{run_id}", response_model=DiagnosticDetail)
def detail(run_id: UUID, current: CurrentSession, store: Store, service: Ai) -> DiagnosticDetail:
    return DiagnosticDetail(
        run=RunResponse.from_snapshot(service.get_run(current.user_id, run_id)),
        trace=DiagnosticTrace.model_validate(store.read(current.user_id, run_id)),
    )


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def create(
    payload: ConversationCreate, current: CurrentSession, store: Store, service: Ai
) -> ConversationResponse:
    chat = service.create(
        current.user_id,
        payload.title,
        offering_id=payload.offering_id,
        connection_id=payload.connection_id,
        demo=payload.demo,
    )
    store.enable(current.user_id, chat.id)
    return ConversationResponse.model_validate(chat)


@router.put("/runs/{run_id}/review", status_code=204, dependencies=[Depends(require_csrf)])
def review(
    run_id: UUID, payload: DiagnosticReview, current: CurrentSession, store: Store, service: Ai
) -> Response:
    service.get_run(current.user_id, run_id)
    store.review(current.user_id, run_id, payload)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.delete("/runs/{run_id}/capture", status_code=204, dependencies=[Depends(require_csrf)])
def clear(run_id: UUID, current: CurrentSession, store: Store, service: Ai) -> Response:
    service.get_run(current.user_id, run_id)
    store.clear(current.user_id, run_id)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
