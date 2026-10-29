from contextlib import contextmanager
from dataclasses import asdict

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from app.modules.academics.presentation.routes import no_store
from app.modules.ai.application.reviews import ReviewConfiguration, ReviewSettingsService
from app.modules.ai.domain.state import AiPersistenceUnavailable
from app.modules.ai.infrastructure.repository import SqlAlchemyAiRepository
from app.modules.ai.infrastructure.review_settings import SqlAlchemyReviewSettings
from app.modules.ai.presentation.routes import Ai
from app.modules.auth.presentation.dependencies import CurrentSession, Database, require_csrf
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication

router = APIRouter(prefix="/api/v1/ai/reviews", tags=["ai"], dependencies=[Depends(no_store)])


class ReviewSettingsResponse(BaseModel):
    configuration: ReviewConfiguration
    version: int
    offering_version: int | None


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
def get_review_settings(current: CurrentSession, database: Database, service: Ai):
    with review_transaction(database):
        return asdict(settings_service(database).get(current.user_id))


@router.put(
    "/settings", response_model=ReviewSettingsResponse, dependencies=[Depends(require_csrf)]
)
def save_review_settings(
    payload: ReviewSettingsUpdate, current: CurrentSession, database: Database, service: Ai
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
        )
