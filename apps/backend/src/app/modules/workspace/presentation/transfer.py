import hmac
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from app.modules.academics.presentation.routes import no_store
from app.modules.auth.presentation.dependencies import (
    CurrentSession,
    Database,
    get_current_session,
    require_csrf,
)
from app.modules.workspace.application.transfer import WorkspaceTransfer
from app.modules.workspace.domain.transfer import (
    MAX_ARCHIVE_BYTES,
    InvalidTransfer,
    WorkspaceArchive,
)
from app.modules.workspace.infrastructure.transfer import SqlAlchemyTransferReceipts
from app.modules.workspace.presentation.database_views import Views

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1/workspace/transfer",
    tags=["workspace transfer"],
    dependencies=[Depends(no_store), Depends(get_current_session)],
)


class ArchiveResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    archive: WorkspaceArchive


class TransferRequest(ArchiveResponse):
    title: str = Field(min_length=1, max_length=200)
    digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class TransferResponse(BaseModel):
    digest: str
    pages: int
    databases: int
    records: int
    views: int
    root_page_id: UUID | None = None


async def read_transfer(request: Request) -> TransferRequest:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_ARCHIVE_BYTES + 4096:
            raise HTTPException(413, "Transfer exceeds 32 MiB.")
    try:
        return TransferRequest.model_validate_json(bytes(body))
    except ValidationError, ValueError, RecursionError:
        raise HTTPException(422, "Invalid page/database transfer format.") from None


Payload = Annotated[TransferRequest, Depends(read_transfer)]


def result(payload: TransferRequest, digest: str, root: UUID | None = None) -> TransferResponse:
    return TransferResponse(
        digest=digest,
        pages=len(payload.archive.pages),
        databases=len(payload.archive.databases),
        records=sum(len(db.records) for db in payload.archive.databases),
        views=sum(len(db.views) for db in payload.archive.databases),
        root_page_id=root,
    )


@router.get("/export", response_model=ArchiveResponse)
def export_workspace(current: CurrentSession, database: Database, views: Views) -> ArchiveResponse:
    with database.begin():
        database.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        try:
            return ArchiveResponse(archive=WorkspaceTransfer(views).export(current.user_id))
        except InvalidTransfer as error:
            raise HTTPException(422, str(error)) from None


def transfer(
    payload: TransferRequest, user_id: UUID, database: Database, views: Views, *, preview: bool
) -> TransferResponse:
    service = WorkspaceTransfer(views, SqlAlchemyTransferReceipts(database))
    with database.begin():
        try:
            digest = service.digest(user_id, payload.archive, payload.title)
            if not preview and (
                payload.digest is None or not hmac.compare_digest(payload.digest, digest)
            ):
                raise HTTPException(409, "Transfer changed. Preview the exact file again.")
            if preview:
                with database.begin_nested() as savepoint:
                    service.copy(user_id, payload.archive, payload.title)
                    savepoint.rollback()
                return result(payload, digest)
            root = service.apply(user_id, payload.archive, payload.title)
            response = result(payload, digest, root)
        except InvalidTransfer as error:
            raise HTTPException(422, str(error)) from None
        except ValueError, KeyError, TypeError, RecursionError:
            raise HTTPException(422, "Invalid references or values in transfer.") from None
    logger.info("workspace.transfer_imported", extra={"user_id": str(user_id)})
    return response


@router.post("/preview", response_model=TransferResponse, dependencies=[Depends(require_csrf)])
async def preview_transfer(
    payload: Payload, current: CurrentSession, database: Database, views: Views
) -> TransferResponse:
    return await run_in_threadpool(
        transfer, payload, current.user_id, database, views, preview=True
    )


@router.post("/import", response_model=TransferResponse, dependencies=[Depends(require_csrf)])
async def import_transfer(
    payload: Payload, current: CurrentSession, database: Database, views: Views
) -> TransferResponse:
    return await run_in_threadpool(
        transfer, payload, current.user_id, database, views, preview=False
    )
