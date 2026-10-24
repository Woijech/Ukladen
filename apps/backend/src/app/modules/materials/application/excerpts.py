from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.modules.materials.application.ports import MaterialRepository
from app.modules.materials.domain.materials import InvalidMaterialInput, MaterialNotFound
from app.modules.users.application.ports import UserAuthentication
from app.modules.users.domain.profile import ProfileUnavailable


@dataclass(frozen=True)
class MaterialExcerpt:
    material_id: UUID
    title: str
    version: int
    text: str
    offset: int
    total_characters: int


class ExtractedTextReader(Protocol):
    """Read a bounded Unicode character range in the caller's metadata snapshot."""

    def read(
        self, user_id: UUID, material_id: UUID, offset: int, limit: int
    ) -> tuple[str, int] | None: ...


class MaterialExcerptService:
    def __init__(
        self, materials: MaterialRepository, users: UserAuthentication, text: ExtractedTextReader
    ) -> None:
        self.materials, self.users, self.text = materials, users, text

    def read(
        self, user_id: UUID, material_id: UUID, offset: int = 0, limit: int = 2000
    ) -> MaterialExcerpt | None:
        if type(offset) is not int or not 0 <= offset <= 2097152:
            raise InvalidMaterialInput()
        if type(limit) is not int or not 1 <= limit <= 2000:
            raise InvalidMaterialInput()
        if not self.users.is_active(user_id):
            raise ProfileUnavailable()
        material = self.materials.get(user_id, material_id)
        if material is None or material.trashed_at is not None:
            raise MaterialNotFound()
        if material.kind != "file" or material.status != "ready":
            return None
        result = self.text.read(user_id, material_id, offset, limit)
        if result is None:
            return None
        text, total = result
        return MaterialExcerpt(material.id, material.title, material.version, text, offset, total)
