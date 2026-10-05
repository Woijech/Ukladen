from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.modules.auth.presentation.dependencies import CurrentSession, Database, require_csrf
from app.modules.users.application.avatar import AvatarService
from app.modules.users.application.ports import AvatarStorage
from app.modules.users.domain.avatar import MAX_AVATAR_BYTES, AvatarTooLarge
from app.modules.users.infrastructure.avatar_image import PillowAvatarImageProcessor
from app.modules.users.infrastructure.repository import SqlAlchemyProfileRepository
from app.modules.users.presentation.schemas import ProfileResponse

router = APIRouter(prefix="/api/v1/users/me/avatar", tags=["users"])


def get_avatars(request: Request, database: Database) -> AvatarService:
    storage: AvatarStorage = request.app.state.avatar_storage
    return AvatarService(
        SqlAlchemyProfileRepository(database), storage, PillowAvatarImageProcessor()
    )


Avatars = Annotated[AvatarService, Depends(get_avatars)]


async def read_avatar_body(request: Request) -> bytes:
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_AVATAR_BYTES:
            raise AvatarTooLarge()
        content.extend(chunk)
    return bytes(content)


@router.put(
    "",
    response_model=ProfileResponse,
    dependencies=[Depends(require_csrf)],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                content_type: {"schema": {"type": "string", "format": "binary"}}
                for content_type in ("image/jpeg", "image/png", "image/webp")
            },
        }
    },
)
async def upload_avatar(
    request: Request,
    current: CurrentSession,
    database: Database,
    avatars: Avatars,
    response: Response,
) -> ProfileResponse:
    content = await read_avatar_body(request)

    def replace() -> ProfileResponse:
        prepared = avatars.prepare(
            current.user_id, content, request.headers.get("content-type", "")
        )
        try:
            with database.begin():
                change = avatars.replace(current.user_id, prepared)
                result = ProfileResponse.from_profile(change.profile)
        except SQLAlchemyError:
            # Use an independent connection; retain the object if commit status is uncertain.
            with suppress(SQLAlchemyError):
                with request.app.state.session_factory() as recovery, recovery.begin():
                    avatars.cleanup_failed_upload(
                        current.user_id, prepared.key, SqlAlchemyProfileRepository(recovery)
                    )
            raise
        except Exception:
            avatars.cleanup(prepared.key)
            raise
        avatars.cleanup(change.previous_key)
        return result

    result = await run_in_threadpool(replace)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("", response_class=Response, responses={200: {"content": {"image/png": {}}}})
def get_avatar(current: CurrentSession, database: Database, avatars: Avatars) -> Response:
    with database.begin():
        content = avatars.get(current.user_id)
    return Response(
        content,
        media_type="image/png",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.delete("", status_code=204, dependencies=[Depends(require_csrf)])
def remove_avatar(current: CurrentSession, database: Database, avatars: Avatars) -> Response:
    with database.begin():
        key = avatars.remove(current.user_id)
    avatars.cleanup(key)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
