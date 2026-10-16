from typing import Protocol
from uuid import UUID

from app.modules.materials.application.service import MaterialService
from app.modules.materials.domain.materials import InvalidMaterialInput, Material
from app.modules.notes.application.service import NoteService
from app.modules.notes.domain.pages import PageMetadata
from app.modules.relations.domain.links import RelationNotFound


class PageMaterialLinks(Protocol):
    def put(self, user_id: UUID, page_id: UUID, material_id: UUID) -> None: ...
    def delete(self, user_id: UUID, page_id: UUID, material_id: UUID) -> bool: ...
    def for_page(self, user_id: UUID, page_id: UUID, limit: int, offset: int) -> list[UUID]: ...
    def for_material(
        self, user_id: UUID, material_id: UUID, limit: int, offset: int
    ) -> list[UUID]: ...


class MaterialRelationService:
    def __init__(
        self, repository: PageMaterialLinks, notes: NoteService, materials: MaterialService
    ) -> None:
        self.repository, self.notes, self.materials = repository, notes, materials

    def link(self, user_id: UUID, page_id: UUID, material_id: UUID) -> Material:
        self.materials.require_user(user_id, write=True)
        self.notes.summary(user_id, page_id, active=True)
        material = self.materials.get(user_id, material_id, active=True)
        self.repository.put(user_id, page_id, material_id)
        return material

    def unlink(self, user_id: UUID, page_id: UUID, material_id: UUID) -> None:
        self.materials.require_user(user_id, write=True)
        if not self.repository.delete(user_id, page_id, material_id):
            raise RelationNotFound()

    @staticmethod
    def pagination(limit: int, offset: int) -> None:
        if not 1 <= limit <= 200 or not 0 <= offset <= 2**31 - 1:
            raise InvalidMaterialInput()

    def for_page(self, user_id: UUID, page_id: UUID, limit: int, offset: int) -> list[Material]:
        self.notes.summary(user_id, page_id)
        self.pagination(limit, offset)
        return [
            self.materials.get(user_id, identifier)
            for identifier in self.repository.for_page(user_id, page_id, limit, offset)
        ]

    def for_material(
        self, user_id: UUID, material_id: UUID, limit: int, offset: int
    ) -> list[PageMetadata]:
        self.materials.get(user_id, material_id)
        self.pagination(limit, offset)
        return [
            self.notes.summary(user_id, identifier)
            for identifier in self.repository.for_material(user_id, material_id, limit, offset)
        ]
