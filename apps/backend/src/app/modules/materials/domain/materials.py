from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Literal
from uuid import UUID

from app.core.urls import http_url

MAX_FILE_BYTES = 25 * 1024 * 1024
USER_STORAGE_BYTES = 1024 * 1024 * 1024
MAX_MATERIALS = 10000
MAX_TEXT_BYTES = 2 * 1024 * 1024
MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
    ".md": "text/markdown",
}
MaterialStatus = Literal["uploading", "pending", "processing", "ready", "failed"]


class InvalidMaterialInput(ValueError):
    pass


class MaterialNotFound(Exception):
    pass


class MaterialConflict(Exception):
    pass


class MaterialTooLarge(Exception):
    pass


class StorageQuotaExceeded(Exception):
    pass


class MaterialStorageUnavailable(Exception):
    pass


class DocumentExtractionError(Exception):
    def __init__(self, code: str = "invalid_document") -> None:
        self.code = code
        super().__init__(code)


def material_title(value: object) -> str:
    if not isinstance(value, str):
        raise InvalidMaterialInput()
    value = value.strip()
    if not 1 <= len(value) <= 200 or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise InvalidMaterialInput()
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise InvalidMaterialInput() from None
    return value


def file_metadata(filename: object, size_bytes: object) -> tuple[str, str, int]:
    filename = material_title(filename)
    extension = PurePosixPath(filename).suffix.lower()
    if "/" in filename or "\\" in filename or extension not in MIME_TYPES:
        raise InvalidMaterialInput()
    if type(size_bytes) is not int or size_bytes < 1:
        raise InvalidMaterialInput()
    if size_bytes > MAX_FILE_BYTES:
        raise MaterialTooLarge()
    return filename, MIME_TYPES[extension], size_bytes


def material_url(value: object) -> str:
    try:
        return http_url(value)
    except ValueError:
        raise InvalidMaterialInput() from None


@dataclass(frozen=True, kw_only=True)
class Material:
    id: UUID
    user_id: UUID
    title: str
    kind: Literal["file", "link"]
    filename: str | None
    media_type: str | None
    size_bytes: int
    url: str | None
    status: MaterialStatus
    version: int
    created_at: datetime
    updated_at: datetime
    trashed_at: datetime | None = None
    error_code: str | None = None
    attempts: int = 0
    lease_token: UUID | None = None
    lease_until: datetime | None = None

    @property
    def storage_key(self) -> str:
        return f"materials/{self.user_id}/{self.id}"


def require_version(material: Material, expected_version: int) -> None:
    if type(expected_version) is not int or expected_version < 1:
        raise InvalidMaterialInput()
    if material.version != expected_version:
        raise MaterialConflict()
