from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.materials.infrastructure.orm import MaterialModel
from app.modules.notes.domain.blocks import document_markdown, parse_document
from app.modules.notes.infrastructure.orm import PageModel
from app.modules.search.domain.chunks import SourceDocument
from app.modules.search.infrastructure.orm import MaterialSearchDocumentModel
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication


class SqlAlchemySourceDocuments:
    """Canonical owner/version checks shared by indexing and retrieval publication."""

    def __init__(self, database: Session):
        self.database = database

    def read(self, user_id: UUID, source: str, source_id: UUID) -> SourceDocument | None:
        if not SqlAlchemyUserAuthentication(self.database).is_active(user_id):
            return None
        if source == "page":
            row = self.database.scalar(
                select(PageModel).where(
                    PageModel.id == source_id,
                    PageModel.user_id == user_id,
                    PageModel.trashed_at.is_(None),
                )
            )
            if row is None:
                return None
            document = parse_document(row.document)
            body = document_markdown(document)
            ranges, offset = [], 0
            for block in document.blocks:
                from app.modules.notes.domain.blocks import PageDocument

                text = document_markdown(PageDocument((block,)))
                start = body.find(text, offset)
                if text and start >= 0:
                    ranges.append((start, start + len(text), f"block:{block.id}"))
                    offset = start + len(text)
            return SourceDocument(
                user_id, "page", row.id, row.version, row.title, body, tuple(ranges)
            )
        if source != "material":
            return None
        result = self.database.execute(
            select(MaterialModel, MaterialSearchDocumentModel)
            .join(
                MaterialSearchDocumentModel,
                (MaterialSearchDocumentModel.material_id == MaterialModel.id)
                & (MaterialSearchDocumentModel.user_id == MaterialModel.user_id),
            )
            .where(
                MaterialModel.id == source_id,
                MaterialModel.user_id == user_id,
                MaterialModel.trashed_at.is_(None),
                MaterialModel.status == "ready",
                MaterialModel.kind == "file",
            )
        ).one_or_none()
        if result is None:
            return None
        material, text = result
        locations = tuple(
            (item["start"], item["end"], f"{item['kind']}:{item['number']}")
            for item in text.locations
        )
        return SourceDocument(
            user_id, "material", material.id, material.version, material.title, text.body, locations
        )
