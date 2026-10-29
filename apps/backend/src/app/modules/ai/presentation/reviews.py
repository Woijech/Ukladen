from contextlib import contextmanager
from dataclasses import asdict
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from app.modules.academics.presentation.routes import no_store
from app.modules.ai.application.reviews import ReviewConfiguration, ReviewSettingsService
from app.modules.ai.domain.state import AiPersistenceUnavailable
from app.modules.ai.infrastructure.repository import SqlAlchemyAiRepository
from app.modules.ai.infrastructure.review_reports import ReviewReports
from app.modules.ai.infrastructure.review_settings import SqlAlchemyReviewSettings
from app.modules.ai.infrastructure.sources import SqlAlchemySourceReader
from app.modules.ai.presentation.routes import Ai
from app.modules.auth.presentation.dependencies import (
    Config,
    CurrentSession,
    Database,
    require_csrf,
)
from app.modules.search.domain.evidence import SourceReference
from app.modules.users.infrastructure.repository import (
    SqlAlchemyProfileRepository,
    SqlAlchemyUserAuthentication,
)

router = APIRouter(prefix="/api/v1/ai/reviews", tags=["ai"], dependencies=[Depends(no_store)])


class ReviewSettingsResponse(BaseModel):
    configuration: ReviewConfiguration
    version: int
    offering_version: int | None
    runtime_enabled: bool = False
    paused_reason: str | None = None
    timezone: str = "UTC"


class ReviewSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    configuration: ReviewConfiguration
    expected_version: int = Field(ge=0)


def settings_service(database) -> ReviewSettingsService:
    return ReviewSettingsService(
        SqlAlchemyReviewSettings(database), SqlAlchemyUserAuthentication(database)
    )


@contextmanager
def review_transaction(database):
    try:
        with database.begin():
            yield
    except SQLAlchemyError as error:
        raise AiPersistenceUnavailable() from error


@router.get("/settings", response_model=ReviewSettingsResponse)
def get_review_settings(current: CurrentSession, database: Database, service: Ai, config: Config):
    with review_transaction(database):
        return asdict(settings_service(database).get(current.user_id)) | runtime_status(
            database, current.user_id, config
        )


@router.put(
    "/settings", response_model=ReviewSettingsResponse, dependencies=[Depends(require_csrf)]
)
def save_review_settings(
    payload: ReviewSettingsUpdate,
    current: CurrentSession,
    database: Database,
    service: Ai,
    config: Config,
):
    with review_transaction(database):
        return asdict(
            settings_service(database).save(
                current.user_id,
                payload.configuration,
                payload.expected_version,
                connections=service.connections,
                ai=SqlAlchemyAiRepository(database),
            )
        ) | runtime_status(database, current.user_id, config)


def runtime_status(database, user_id, config):
    from app.modules.ai.infrastructure.review_models import ReviewSettingsModel

    row = database.get(ReviewSettingsModel, user_id)
    profile = SqlAlchemyProfileRepository(database).get_active(user_id)
    return {
        "runtime_enabled": config.ai_reviews_enabled,
        "paused_reason": row.state.get("paused") if row else None,
        "timezone": profile.timezone if profile else "UTC",
    }


class ReviewResponse(BaseModel):
    id: UUID
    kind: Literal["daily", "weekly", "warnings"]
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    created_at: AwareDatetime
    expires_at: AwareDatetime
    content: str | None
    sources: tuple[SourceReference, ...]
    stale: bool


class ReviewDiscussionResponse(BaseModel):
    conversation_id: UUID


def report_service(request: Request, config: Config, service: Ai):
    return ReviewReports(
        service,
        SqlAlchemySourceReader(
            request.app.state.session_factory,
            request.app.state.academic_provider,
            config.schedule_sync_interval_seconds,
        ),
    )


@router.get("/{review_id}", response_model=ReviewResponse)
def get_review(
    review_id: UUID, request: Request, current: CurrentSession, config: Config, service: Ai
):
    return report_service(request, config, service).get(current.user_id, review_id)


@router.post(
    "/{review_id}/discuss",
    response_model=ReviewDiscussionResponse,
    dependencies=[Depends(require_csrf)],
)
def discuss_review(
    review_id: UUID, request: Request, current: CurrentSession, config: Config, service: Ai
):
    return report_service(request, config, service).discuss(current.user_id, review_id)
