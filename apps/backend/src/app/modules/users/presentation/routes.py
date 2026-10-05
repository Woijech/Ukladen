from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.modules.auth.domain.errors import InvalidSession
from app.modules.auth.presentation.dependencies import CurrentSession, Database, require_csrf
from app.modules.users.application.ports import AvatarStorageUnavailable
from app.modules.users.application.profile import ProfileService
from app.modules.users.domain.avatar import AvatarNotFound, AvatarTooLarge, InvalidAvatar
from app.modules.users.domain.profile import ProfileUnavailable
from app.modules.users.infrastructure.repository import SqlAlchemyProfileRepository
from app.modules.users.presentation.avatar import router as avatar_router
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
        result = ProfileResponse.from_profile(profiles.get(current.user_id))
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
        result = ProfileResponse.from_profile(
            profiles.update(current.user_id, payload.model_dump(exclude_unset=True))
        )
    response.headers["Cache-Control"] = "no-store"
    return result


def install_users(application: FastAPI) -> None:
    # Canonical eligibility failures use the existing auth response and cookie clearing.
    application.add_exception_handler(
        ProfileUnavailable, application.exception_handlers[InvalidSession]
    )

    def avatar_error(request: Request, error: Exception) -> JSONResponse:
        if isinstance(error, AvatarTooLarge):
            status, detail = 413, "Avatar exceeds the size limit."
        elif isinstance(error, InvalidAvatar):
            status, detail = 422, "Invalid avatar image."
        elif isinstance(error, AvatarNotFound):
            status, detail = 404, "Avatar not found."
        else:
            status, detail = 503, "Service unavailable."
        return JSONResponse(
            {"detail": detail}, status_code=status, headers={"Cache-Control": "no-store"}
        )

    for error_type in (AvatarTooLarge, InvalidAvatar, AvatarNotFound, AvatarStorageUnavailable):
        application.add_exception_handler(error_type, avatar_error)
    application.include_router(router)
    application.include_router(avatar_router)
