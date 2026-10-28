import logging
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.logging import log_failure
from app.modules.academics.presentation.routes import no_store
from app.modules.ai.application.access import AiAccessStatus
from app.modules.ai.application.actions import (
    ActionBatch,
    ActionService,
    Proposal,
    ProposalDecision,
)
from app.modules.ai.application.connections import ConnectionAccess, ModelOption
from app.modules.ai.application.lifecycle import AiService
from app.modules.ai.application.source_queries import SourceQuery
from app.modules.ai.application.usage import UsageReport
from app.modules.ai.domain.connections import ConnectionLimited, ConnectionUnavailable, UsageLimited
from app.modules.ai.domain.state import (
    AiConflict,
    AiNotFound,
    AiPersistenceUnavailable,
    InvalidAiState,
)
from app.modules.ai.infrastructure.actions import SqlAlchemyActionTransactions
from app.modules.ai.infrastructure.connections import FileConnectionConfiguration
from app.modules.ai.infrastructure.lifecycle import PostgresAgentRunners, SqlAlchemyAiTransactions
from app.modules.ai.infrastructure.providers import OpenRouterModels
from app.modules.ai.infrastructure.sources import SqlAlchemySourceReader
from app.modules.ai.infrastructure.usage import SqlAlchemyUsageReader
from app.modules.ai.presentation.schemas import (
    ConnectionCreate,
    ConnectionList,
    ConnectionResponse,
    ConversationCreate,
    ConversationList,
    ConversationResponse,
    ConversationState,
    DocumentProgressResponse,
    IndexStatusResponse,
    MessageList,
    MessageResponse,
    MessageSubmit,
    PreferencesResponse,
    PreferencesUpdate,
    ProposalResponse,
    RunResponse,
)
from app.modules.ai.presentation.streaming import stream_response
from app.modules.auth.presentation.dependencies import (
    Config,
    CurrentSession,
    get_current_session,
    require_csrf,
)
from app.modules.search.application.evidence import EvidenceResult
from app.modules.search.infrastructure.runtime import embedding_provider

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1/ai", tags=["ai"], dependencies=[Depends(no_store), Depends(get_current_session)]
)


def get_ai(request: Request, settings: Config) -> AiService:
    if not settings.ai_enabled:
        raise HTTPException(503, "AI is disabled.", headers={"Cache-Control": "no-store"})
    sessions = request.app.state.session_factory
    transactions = SqlAlchemyAiTransactions(sessions)
    access = (
        ConnectionAccess(FileConnectionConfiguration(settings.ai_connections_file))
        if settings.ai_connections_file is not None
        else None
    )
    sources = SqlAlchemySourceReader(
        sessions,
        request.app.state.academic_provider,
        settings.schedule_sync_interval_seconds,
        embeddings=embedding_provider(settings.search_embeddings_directory)
        if settings.search_embeddings_directory
        else None,
    )
    actions = (
        ActionService(SqlAlchemyActionTransactions(sources), connections=access)
        if settings.ai_actions_enabled
        else None
    )
    return AiService(
        transactions,
        PostgresAgentRunners(
            sessions,
            real_models=OpenRouterModels(transactions, access) if access else None,
            sources=sources,
            actions_enabled=settings.ai_actions_enabled,
        ),
        provider=settings.ai_llm_provider,
        model=settings.ai_llm_model,
        connections=access,
        actions=actions,
    )


Ai = Annotated[AiService, Depends(get_ai)]


def get_actions(service: Ai, settings: Config) -> ActionService:
    if not settings.ai_actions_enabled or service.actions is None:
        raise HTTPException(503, "AI actions are disabled.")
    return service.actions


Actions = Annotated[ActionService, Depends(get_actions)]


@router.get("/conversations/{conversation_id}/proposals", response_model=list[ProposalResponse])
def list_proposals(
    conversation_id: UUID,
    current: CurrentSession,
    service: Actions,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10000),
) -> list[Proposal]:
    return service.list(current.user_id, conversation_id, limit, offset)


@router.post(
    "/proposals/{proposal_id}/decision",
    response_model=ProposalResponse,
    dependencies=[Depends(require_csrf)],
)
def decide_proposal(
    proposal_id: UUID,
    payload: ProposalDecision,
    current: CurrentSession,
    service: Actions,
) -> Proposal:
    return service.decide(current.user_id, proposal_id, payload)


@router.post(
    "/proposals/{proposal_id}/revise",
    response_model=ProposalResponse,
    dependencies=[Depends(require_csrf)],
)
def revise_proposal(
    proposal_id: UUID, payload: ActionBatch, current: CurrentSession, service: Actions
) -> Proposal:
    return service.revise(current.user_id, proposal_id, payload)


@router.get("/access", response_model=AiAccessStatus)
def access_status(current: CurrentSession, service: Ai) -> AiAccessStatus:
    return service.access_status(current.user_id)


@router.get("/usage", response_model=UsageReport)
def usage(
    request: Request,
    current: CurrentSession,
    service: Ai,
    days: int = Query(7, ge=7, le=30),
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10000),
) -> UsageReport:
    return SqlAlchemyUsageReader(request.app.state.session_factory).read(
        current.user_id,
        date_from,
        date_to,
        days,
        limit,
        offset,
    )


@router.post("/sources/read", response_model=EvidenceResult, dependencies=[Depends(require_csrf)])
def read_source(
    payload: SourceQuery,
    request: Request,
    settings: Config,
    current: CurrentSession,
    service: Ai,
) -> EvidenceResult:
    return SqlAlchemySourceReader(
        request.app.state.session_factory,
        request.app.state.academic_provider,
        settings.schedule_sync_interval_seconds,
        embeddings=embedding_provider(settings.search_embeddings_directory)
        if settings.search_embeddings_directory
        else None,
    ).read(current.user_id, payload)


@router.get("/runs/{run_id}/document-progress", response_model=DocumentProgressResponse | None)
def document_progress(
    run_id: UUID, request: Request, current: CurrentSession, service: Ai
) -> dict | None:
    from app.modules.ai.infrastructure.document_jobs import SqlAlchemyDocumentSteps

    return SqlAlchemyDocumentSteps(request.app.state.session_factory, service).progress(
        current.user_id, run_id
    )


@router.get("/sources/{source}/{source_id}/index", response_model=IndexStatusResponse)
def source_index_status(
    source: Literal["page", "material"],
    source_id: UUID,
    request: Request,
    settings: Config,
    current: CurrentSession,
    service: Ai,
) -> dict:
    from app.modules.search.infrastructure.status import index_status

    status = index_status(
        request.app.state.session_factory,
        settings.search_embeddings_directory,
        current.user_id,
        source,
        source_id,
    )
    if status is None:
        raise AiNotFound()
    return status


@router.post(
    "/sources/{source}/{source_id}/index/retry",
    response_model=IndexStatusResponse,
    dependencies=[Depends(require_csrf)],
)
def retry_source_index(
    source: Literal["page", "material"],
    source_id: UUID,
    request: Request,
    settings: Config,
    current: CurrentSession,
    service: Ai,
) -> dict:
    from app.modules.search.infrastructure.indexing import SqlAlchemyIndexStore
    from app.modules.search.infrastructure.status import index_status

    if (
        index_status(
            request.app.state.session_factory,
            settings.search_embeddings_directory,
            current.user_id,
            source,
            source_id,
        )
        is None
    ):
        raise AiNotFound()
    if settings.search_embeddings_directory:
        provider = embedding_provider(settings.search_embeddings_directory)
        SqlAlchemyIndexStore(request.app.state.session_factory, provider.profile).retry(
            current.user_id, source, source_id
        )
    status = index_status(
        request.app.state.session_factory,
        settings.search_embeddings_directory,
        current.user_id,
        source,
        source_id,
    )
    if status is None:
        raise AiNotFound()
    return status


@router.get("/preferences", response_model=PreferencesResponse)
def preferences(current: CurrentSession, service: Ai) -> PreferencesResponse:
    return PreferencesResponse.model_validate(service.preferences(current.user_id))


@router.put(
    "/preferences", response_model=PreferencesResponse, dependencies=[Depends(require_csrf)]
)
def save_preferences(
    payload: PreferencesUpdate, current: CurrentSession, service: Ai
) -> PreferencesResponse:
    return PreferencesResponse.model_validate(
        service.save_preferences(
            current.user_id,
            payload.instructions,
            payload.expected_version,
        )
    )


@router.get("/conversations/{conversation_id}/state", response_model=ConversationState)
def conversation_state(
    conversation_id: UUID, current: CurrentSession, service: Ai
) -> ConversationState:
    conversation, run = service.conversation_state(current.user_id, conversation_id)
    return ConversationState(
        conversation=ConversationResponse.model_validate(conversation),
        run=RunResponse.from_snapshot(service.get_run(current.user_id, run.id)) if run else None,
    )


@router.post(
    "/conversations/{conversation_id}/messages/stream", dependencies=[Depends(require_csrf)]
)
def submit_stream(
    conversation_id: UUID, payload: MessageSubmit, current: CurrentSession, service: Ai
) -> StreamingResponse:
    request = payload.agent_input(conversation_id)
    run, created = service.admit(current.user_id, request, payload.submission_id)
    return stream_response(service, run, request, created and not request.full_sources)


@router.post(
    "/conversations",
    status_code=201,
    response_model=ConversationResponse,
    dependencies=[Depends(require_csrf)],
)
def create_conversation(
    payload: ConversationCreate, current: CurrentSession, service: Ai
) -> ConversationResponse:
    return ConversationResponse.model_validate(
        service.create(
            current.user_id,
            payload.title,
            offering_id=payload.offering_id,
            connection_id=payload.connection_id,
            demo=payload.demo,
        )
    )


@router.get("/models", response_model=list[ModelOption])
def list_models(current: CurrentSession, service: Ai) -> list[ModelOption]:
    return service.models(current.user_id)


@router.get("/connections", response_model=ConnectionList)
def list_connections(current: CurrentSession, service: Ai) -> ConnectionList:
    return ConnectionList(
        items=[
            ConnectionResponse.model_validate(item)
            for item in service.personal_connections(current.user_id)
        ]
    )


@router.post(
    "/connections",
    status_code=201,
    response_model=ConnectionResponse,
    dependencies=[Depends(require_csrf)],
)
def add_connection(
    payload: ConnectionCreate, current: CurrentSession, service: Ai
) -> ConnectionResponse:
    return ConnectionResponse.model_validate(
        service.connect(current.user_id, payload.label, payload.key.get_secret_value())
    )


@router.delete(
    "/connections/{connection_id}", status_code=204, dependencies=[Depends(require_csrf)]
)
def disconnect_connection(connection_id: UUID, current: CurrentSession, service: Ai) -> Response:
    service.disconnect(current.user_id, connection_id)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post(
    "/connections/{connection_id}/rotate", status_code=204, dependencies=[Depends(require_csrf)]
)
def rotate_connection(connection_id: UUID, current: CurrentSession, service: Ai) -> Response:
    service.rotate_connection(current.user_id, connection_id)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


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
    recent: bool = False,
    before: int | None = Query(None, ge=1, le=2**63 - 1),
) -> MessageList:
    return MessageList(
        items=[
            MessageResponse.model_validate(item)
            for item in (
                service.recent_history(current.user_id, conversation_id, before, limit)
                if recent or before is not None
                else service.history(current.user_id, conversation_id, after, limit)
            )
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
        headers = {"Cache-Control": "no-store"}
        if isinstance(error, AiNotFound):
            status, detail = 404, "AI resource not found."
        elif isinstance(error, AiConflict):
            status, detail = 409, "AI state changed or execution is unavailable."
        elif isinstance(error, InvalidAiState):
            status, detail = 422, "Invalid AI input."
        elif isinstance(error, UsageLimited):
            status, detail = 429, "AI usage limit reached."
            headers["Retry-After"] = str(error.retry_after)
        elif isinstance(error, ConnectionLimited):
            status, detail = 429, "AI connection request limit reached."
            headers["Retry-After"] = str(error.retry_after)
        elif isinstance(error, ConnectionUnavailable):
            status, detail = 503, "AI connection is unavailable."
        else:
            status, detail = 503, "AI storage is unavailable."
        log_failure(logger, "ai.operation_rejected", error, level=logging.WARNING)
        return JSONResponse({"detail": detail}, status_code=status, headers=headers)

    for error in (
        AiNotFound,
        AiConflict,
        AiPersistenceUnavailable,
        InvalidAiState,
        ConnectionUnavailable,
        ConnectionLimited,
    ):
        application.add_exception_handler(error, ai_error)
    application.include_router(router)
