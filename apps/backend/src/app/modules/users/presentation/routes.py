from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Response

from app.modules.auth.domain.errors import InvalidSession
from app.modules.auth.presentation.dependencies import CurrentSession, Database, require_csrf
from app.modules.users.application.profile import ProfileService
from app.modules.users.domain.profile import ProfileUnavailable
from app.modules.users.infrastructure.repository import SqlAlchemyProfileRepository
from app.modules.users.presentation.schemas import ProfilePatch, ProfileResponse

router = APIRouter(prefix="/api/v1/users", tags=["users"])


def get_profiles(database: Database) -> ProfileService:
    return ProfileService(SqlAlchemyProfileRepository(database))


Profiles = Annotated[ProfileService, Depends(get_profiles)]


@router.get("/me", response_model=ProfileResponse)
def get_profile(
    current: CurrentSession, database: Database, profiles: Profiles, response: Response
) -> ProfileResponse:
    with database.begin():
        result = ProfileResponse.model_validate(profiles.get(current.user_id))
    response.headers["Cache-Control"] = "no-store"
    return result


@router.patch("/me", response_model=ProfileResponse, dependencies=[Depends(require_csrf)])
def update_profile(
    payload: ProfilePatch,
    current: CurrentSession,
    database: Database,
    profiles: Profiles,
    response: Response,
) -> ProfileResponse:
    with database.begin():
        result = ProfileResponse.model_validate(
            profiles.update(current.user_id, payload.model_dump(exclude_unset=True))
        )
    response.headers["Cache-Control"] = "no-store"
    return result


def install_users(application: FastAPI) -> None:
    # Canonical eligibility failures use the existing auth response and cookie clearing.
    application.add_exception_handler(
        ProfileUnavailable, application.exception_handlers[InvalidSession]
    )
    application.include_router(router)
