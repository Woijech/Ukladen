from collections.abc import Iterator
from tempfile import SpooledTemporaryFile
from typing import Annotated, BinaryIO, cast
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.modules.academics.presentation.routes import no_store
from app.modules.auth.presentation.dependencies import (
    CurrentSession,
    Database,
    get_current_session,
    require_csrf,
)
from app.modules.materials.application.service import MaterialService
from app.modules.materials.domain.materials import (
    MAX_FILE_BYTES,
    InvalidMaterialInput,
    MaterialConflict,
    MaterialNotFound,
    MaterialStorageUnavailable,
    MaterialTooLarge,
    StorageQuotaExceeded,
)
from app.modules.materials.infrastructure.repository import SqlAlchemyMaterialRepository
from app.modules.materials.presentation.schemas import (
    LinkCreate,
    MaterialListResponse,
    MaterialPatch,
    MaterialResponse,
    StorageUsageResponse,
    UploadCreate,
    VersionRequest,
)
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication

router = APIRouter(
    prefix="/api/v1/materials",
    tags=["materials"],
    dependencies=[Depends(get_current_session), Depends(no_store)],
)


def get_materials(request: Request, database: Database) -> MaterialService:
    return MaterialService(
        SqlAlchemyMaterialRepository(database),
        SqlAlchemyUserAuthentication(database),
        request.app.state.material_storage,
    )


Materials = Annotated[MaterialService, Depends(get_materials)]


@router.post(
    "/uploads",
    status_code=201,
    response_model=MaterialResponse,
    dependencies=[Depends(require_csrf)],
)
def create_upload(
    payload: UploadCreate, current: CurrentSession, database: Database, materials: Materials
) -> MaterialResponse:
    with database.begin():
        result = MaterialResponse.model_validate(
            materials.create_upload(current.user_id, **payload.model_dump())
        )
    return result


@router.post(
    "/links", status_code=201, response_model=MaterialResponse, dependencies=[Depends(require_csrf)]
)
def create_link(
    payload: LinkCreate, current: CurrentSession, database: Database, materials: Materials
) -> MaterialResponse:
    with database.begin():
        result = MaterialResponse.model_validate(
            materials.create_link(current.user_id, **payload.model_dump())
        )
    return result


@router.get("/storage", response_model=StorageUsageResponse)
def storage_usage(
    current: CurrentSession, database: Database, materials: Materials
) -> StorageUsageResponse:
    with database.begin():
        used, count = materials.usage(current.user_id)
        return StorageUsageResponse(used_bytes=used, material_count=count)


@router.get("", response_model=MaterialListResponse)
def list_materials(
    current: CurrentSession,
    database: Database,
    materials: Materials,
    trashed: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0,
) -> MaterialListResponse:
    with database.begin():
        return MaterialListResponse(
            items=[
                MaterialResponse.model_validate(item)
                for item in materials.list(current.user_id, trashed, limit, offset)
            ],
            limit=limit,
            offset=offset,
        )


@router.get("/{material_id}", response_model=MaterialResponse)
def get_material(
    material_id: UUID, current: CurrentSession, database: Database, materials: Materials
) -> MaterialResponse:
    with database.begin():
        return MaterialResponse.model_validate(materials.get(current.user_id, material_id))


@router.put(
    "/{material_id}/content",
    response_model=MaterialResponse,
    dependencies=[Depends(require_csrf)],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
        }
    },
)
async def upload_content(
    material_id: UUID,
    request: Request,
    current: CurrentSession,
    database: Database,
    materials: Materials,
) -> MaterialResponse:
    with cast(BinaryIO, SpooledTemporaryFile(max_size=1024 * 1024)) as body:
        total = 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise MaterialTooLarge()
            await run_in_threadpool(body.write, chunk)
        body.seek(0)

        def finalize() -> MaterialResponse:
            with database.begin():
                result = MaterialResponse.model_validate(
                    materials.upload(
                        current.user_id, material_id, body, request.headers.get("content-type", "")
                    )
                )
            return result

        return await run_in_threadpool(finalize)


def stream_body(body: BinaryIO) -> Iterator[bytes]:
    try:
        while chunk := body.read(64 * 1024):
            yield chunk
    finally:
        body.close()


@router.get("/{material_id}/content")
def download_content(
    material_id: UUID, current: CurrentSession, database: Database, materials: Materials
) -> StreamingResponse:
    body = None
    try:
        with database.begin():
            material, body = materials.download(current.user_id, material_id)
    except Exception:
        if body is not None:
            body.close()
        raise
    return StreamingResponse(
        stream_body(body),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''"
            + quote(material.filename or "download", safe=""),
            "Content-Length": str(material.size_bytes),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.patch(
    "/{material_id}", response_model=MaterialResponse, dependencies=[Depends(require_csrf)]
)
def update_material(
    material_id: UUID,
    payload: MaterialPatch,
    current: CurrentSession,
    database: Database,
    materials: Materials,
) -> MaterialResponse:
    with database.begin():
        result = MaterialResponse.model_validate(
            materials.update(
                current.user_id,
                material_id,
                payload.model_dump(exclude_unset=True, exclude={"expected_version"}),
                payload.expected_version,
            )
        )
    return result


@router.post(
    "/{material_id}/trash", response_model=MaterialResponse, dependencies=[Depends(require_csrf)]
)
def trash_material(
    material_id: UUID,
    payload: VersionRequest,
    current: CurrentSession,
    database: Database,
    materials: Materials,
) -> MaterialResponse:
    with database.begin():
        result = MaterialResponse.model_validate(
            materials.lifecycle(
                current.user_id, material_id, payload.expected_version, restore=False
            )
        )
    return result


@router.post(
    "/{material_id}/restore", response_model=MaterialResponse, dependencies=[Depends(require_csrf)]
)
def restore_material(
    material_id: UUID,
    payload: VersionRequest,
    current: CurrentSession,
    database: Database,
    materials: Materials,
) -> MaterialResponse:
    with database.begin():
        result = MaterialResponse.model_validate(
            materials.lifecycle(
                current.user_id, material_id, payload.expected_version, restore=True
            )
        )
    return result


@router.post(
    "/{material_id}/retry", response_model=MaterialResponse, dependencies=[Depends(require_csrf)]
)
def retry_material(
    material_id: UUID,
    payload: VersionRequest,
    current: CurrentSession,
    database: Database,
    materials: Materials,
) -> MaterialResponse:
    with database.begin():
        result = MaterialResponse.model_validate(
            materials.retry(current.user_id, material_id, payload.expected_version)
        )
    return result


def install_materials(application: FastAPI) -> None:
    def material_error(request: Request, error: Exception) -> JSONResponse:
        status, detail = 409, "Material changed or operation is unavailable."
        if isinstance(error, InvalidMaterialInput):
            status, detail = 422, "Invalid material input, file type or upload size."
        elif isinstance(error, MaterialNotFound):
            status, detail = 404, "Material not found."
        elif isinstance(error, MaterialTooLarge):
            status, detail = 413, "File exceeds the 25 MiB limit."
        elif isinstance(error, StorageQuotaExceeded):
            status, detail = 409, "Material storage quota or count limit exceeded."
        elif isinstance(error, MaterialStorageUnavailable):
            status, detail = 503, "Material storage is unavailable."
        return JSONResponse(
            {"detail": detail}, status_code=status, headers={"Cache-Control": "no-store"}
        )

    for error in (
        InvalidMaterialInput,
        MaterialNotFound,
        MaterialConflict,
        MaterialTooLarge,
        StorageQuotaExceeded,
        MaterialStorageUnavailable,
    ):
        application.add_exception_handler(error, material_error)
    application.include_router(router)
