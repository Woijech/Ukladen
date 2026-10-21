import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from app.core.logging import log_failure
from app.modules.academics.presentation.routes import no_store
from app.modules.ai.application.lifecycle import AiService
from app.modules.ai.domain.state import (
    AiConflict,
    AiNotFound,
    AiPersistenceUnavailable,
    InvalidAiState,
)
from app.modules.ai.infrastructure.lifecycle import PostgresAgentRunners, SqlAlchemyAiTransactions
from app.modules.ai.presentation.schemas import (
    ConversationCreate,
    ConversationList,
    ConversationResponse,
    MessageList,
    MessageResponse,
    MessageSubmit,
    RunResponse,
)
from app.modules.auth.presentation.dependencies import (
    Config,
    CurrentSession,
    get_current_session,
    require_csrf,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1/ai", tags=["ai"], dependencies=[Depends(no_store), Depends(get_current_session)]
)


def get_ai(request: Request, settings: Config) -> AiService:
    if not settings.ai_enabled:
        raise HTTPException(503, "AI is disabled.", headers={"Cache-Control": "no-store"})
    sessions = request.app.state.session_factory
    return AiService(
        SqlAlchemyAiTransactions(sessions),
        PostgresAgentRunners(sessions),
        provider=settings.ai_llm_provider,
        model=settings.ai_llm_model,
    )


Ai = Annotated[AiService, Depends(get_ai)]


@router.post(
    "/conversations",
    status_code=201,
    response_model=ConversationResponse,
    dependencies=[Depends(require_csrf)],
)
def create_conversation(
    payload: ConversationCreate, current: CurrentSession, service: Ai
) -> ConversationResponse:
    return ConversationResponse.model_validate(service.create(current.user_id, payload.title))


@router.get("/conversations", response_model=ConversationList)
def list_conversations(
    current: CurrentSession,
    service: Ai,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0, le=2**31 - 1),
) -> ConversationList:
    return ConversationList(
        items=[
            ConversationResponse.model_validate(item)
            for item in service.list(current.user_id, limit, offset)
        ]
    )


@router.get("/conversations/{conversation_id}/messages", response_model=MessageList)
def history(
    conversation_id: UUID,
    current: CurrentSession,
    service: Ai,
    after: int = Query(0, ge=0, le=2**63 - 1),
    limit: int = Query(100, ge=1, le=200),
) -> MessageList:
    return MessageList(
        items=[
            MessageResponse.model_validate(item)
            for item in service.history(current.user_id, conversation_id, after, limit)
        ]
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=RunResponse,
    dependencies=[Depends(require_csrf)],
)
def submit_message(
    conversation_id: UUID, payload: MessageSubmit, current: CurrentSession, service: Ai
) -> RunResponse:
    return RunResponse.from_snapshot(
        service.submit(current.user_id, payload.agent_input(conversation_id), payload.submission_id)
    )


@router.get("/runs/{run_id}", response_model=RunResponse)
def get_run(run_id: UUID, current: CurrentSession, service: Ai) -> RunResponse:
    return RunResponse.from_snapshot(service.get_run(current.user_id, run_id))


@router.post(
    "/runs/{run_id}/cancel", response_model=RunResponse, dependencies=[Depends(require_csrf)]
)
def cancel_run(run_id: UUID, current: CurrentSession, service: Ai) -> RunResponse:
    return RunResponse.from_snapshot(service.cancel(current.user_id, run_id))


@router.delete(
    "/conversations/{conversation_id}", status_code=204, dependencies=[Depends(require_csrf)]
)
def delete_conversation(conversation_id: UUID, current: CurrentSession, service: Ai) -> Response:
    service.delete(current.user_id, conversation_id)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


def install_ai(application: FastAPI) -> None:
    def ai_error(request: Request, error: Exception) -> JSONResponse:
        if isinstance(error, AiNotFound):
            status, detail = 404, "AI resource not found."
        elif isinstance(error, AiConflict):
            status, detail = 409, "AI state changed or execution is unavailable."
        elif isinstance(error, InvalidAiState):
            status, detail = 422, "Invalid AI input."
        else:
            status, detail = 503, "AI storage is unavailable."
        log_failure(logger, "ai.operation_rejected", error, level=logging.WARNING)
        return JSONResponse(
            {"detail": detail}, status_code=status, headers={"Cache-Control": "no-store"}
        )

    for error in (AiNotFound, AiConflict, AiPersistenceUnavailable, InvalidAiState):
        application.add_exception_handler(error, ai_error)
    application.include_router(router)
