from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import BinaryIO
from uuid import UUID, uuid4

from app.modules.materials.application.ports import MaterialRepository, MaterialStorage
from app.modules.materials.domain.materials import (
    MAX_MATERIALS,
    USER_STORAGE_BYTES,
    InvalidMaterialInput,
    Material,
    MaterialConflict,
    MaterialNotFound,
    StorageQuotaExceeded,
    file_metadata,
    material_title,
    material_url,
    require_version,
)
from app.modules.users.application.ports import UserAuthentication
from app.modules.users.domain.profile import ProfileUnavailable


class MaterialService:
    """Caller-owned transactions; uploads reserve quota before contacting object storage."""

    def __init__(
        self,
        repository: MaterialRepository,
        users: UserAuthentication,
        storage: MaterialStorage,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.repository, self.users, self.storage, self.now = repository, users, storage, now

    def require_user(self, user_id: UUID, *, write: bool = False) -> None:
        active = self.users.lock_active(user_id) if write else self.users.is_active(user_id)
        if not active:
            raise ProfileUnavailable()

    def usage(self, user_id: UUID) -> tuple[int, int]:
        self.require_user(user_id)
        return self.repository.usage(user_id)

    def reserve(self, user_id: UUID, size: int) -> None:
        self.require_user(user_id, write=True)
        used, count = self.repository.usage(user_id)
        if used + size > USER_STORAGE_BYTES or count >= MAX_MATERIALS:
            raise StorageQuotaExceeded()

    def create_upload(
        self, user_id: UUID, filename: str, size_bytes: int, title: str | None = None
    ) -> Material:
        filename, media_type, size = file_metadata(filename, size_bytes)
        title = material_title(title if title is not None else filename)
        self.reserve(user_id, size)
        now = self.now()
        material = Material(
            id=uuid4(),
            user_id=user_id,
            title=title,
            kind="file",
            filename=filename,
            media_type=media_type,
            size_bytes=size,
            url=None,
            status="uploading",
            version=1,
            created_at=now,
            updated_at=now,
        )
        self.repository.create(material)
        return material

    def create_link(self, user_id: UUID, title: str, url: str) -> Material:
        title, url = material_title(title), material_url(url)
        self.reserve(user_id, 0)
        now = self.now()
        material = Material(
            id=uuid4(),
            user_id=user_id,
            title=title,
            kind="link",
            filename=None,
            media_type=None,
            size_bytes=0,
            url=url,
            status="ready",
            version=1,
            created_at=now,
            updated_at=now,
        )
        self.repository.create(material)
        return material

    def get(self, user_id: UUID, material_id: UUID, *, active: bool = False) -> Material:
        self.require_user(user_id)
        material = self.repository.get(user_id, material_id)
        if material is None:
            raise MaterialNotFound()
        if active and material.trashed_at is not None:
            raise MaterialConflict()
        return material

    def list(
        self, user_id: UUID, trashed: bool = False, limit: int = 100, offset: int = 0
    ) -> list[Material]:
        self.require_user(user_id)
        if (
            type(trashed) is not bool
            or type(limit) is not int
            or type(offset) is not int
            or not (1 <= limit <= 200 and 0 <= offset <= 2**31 - 1)
        ):
            raise InvalidMaterialInput()
        return self.repository.list(user_id, trashed, limit, offset)

    def upload(self, user_id: UUID, material_id: UUID, body: BinaryIO, media_type: str) -> Material:
        self.require_user(user_id, write=True)
        material = self.get(user_id, material_id, active=True)
        if material.status != "uploading" or self.now() >= material.created_at + timedelta(hours=1):
            raise MaterialConflict()
        body.seek(0, 2)
        size = body.tell()
        body.seek(0)
        header = body.read(8)
        body.seek(0)
        if (
            size != material.size_bytes
            or media_type.split(";", 1)[0].strip() != material.media_type
        ):
            raise InvalidMaterialInput()
        if (material.media_type == "application/pdf" and not header.startswith(b"%PDF-")) or (
            material.filename
            and material.filename.lower().endswith((".docx", ".pptx"))
            and not header.startswith(b"PK\x03\x04")
        ):
            raise InvalidMaterialInput()
        assert material.media_type is not None
        self.storage.put(material.storage_key, body, size, material.media_type)
        updated = replace(
            material, status="pending", version=material.version + 1, updated_at=self.now()
        )
        self.repository.save(updated, material.version)
        return updated

    def download(self, user_id: UUID, material_id: UUID) -> tuple[Material, BinaryIO]:
        material = self.get(user_id, material_id, active=True)
        if material.kind != "file" or material.status == "uploading":
            raise MaterialConflict()
        body = self.storage.get(material.storage_key, material.size_bytes)
        if body is None:
            raise MaterialNotFound()
        return material, body

    def update(
        self, user_id: UUID, material_id: UUID, changes: Mapping[str, object], expected_version: int
    ) -> Material:
        self.require_user(user_id, write=True)
        material = self.get(user_id, material_id, active=True)
        require_version(material, expected_version)
        if (
            not changes
            or changes.keys() - {"title", "url"}
            or ("url" in changes and material.kind != "link")
        ):
            raise InvalidMaterialInput()
        updated = replace(
            material,
            title=material_title(changes.get("title", material.title)),
            url=material_url(changes["url"]) if "url" in changes else material.url,
            version=material.version + 1,
            updated_at=self.now(),
        )
        self.repository.save(updated, expected_version)
        return updated

    def lifecycle(
        self, user_id: UUID, material_id: UUID, expected_version: int, *, restore: bool
    ) -> Material:
        self.require_user(user_id, write=True)
        material = self.get(user_id, material_id)
        require_version(material, expected_version)
        now = self.now()
        if (
            restore
            and material.trashed_at is not None
            and now >= material.trashed_at + timedelta(days=30)
        ):
            raise MaterialConflict()
        if (material.trashed_at is None) == restore:
            return material
        updated = replace(
            material,
            trashed_at=None if restore else now,
            version=material.version + 1,
            updated_at=now,
        )
        self.repository.save(updated, expected_version)
        return updated

    def retry(self, user_id: UUID, material_id: UUID, expected_version: int) -> Material:
        self.require_user(user_id, write=True)
        material = self.get(user_id, material_id, active=True)
        require_version(material, expected_version)
        if material.kind != "file" or material.status != "failed":
            raise MaterialConflict()
        updated = replace(
            material,
            status="pending",
            attempts=0,
            error_code=None,
            version=material.version + 1,
            updated_at=self.now(),
        )
        self.repository.save(updated, expected_version)
        return updated
