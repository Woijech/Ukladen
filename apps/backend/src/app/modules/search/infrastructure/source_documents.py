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

    def needs_locations(self, user_id: UUID, source_id: UUID) -> bool:
        row = self.database.execute(
            select(MaterialModel.filename, MaterialSearchDocumentModel.extraction_revision)
            .join(
                MaterialSearchDocumentModel,
                MaterialSearchDocumentModel.material_id == MaterialModel.id,
            )
            .where(
                MaterialModel.id == source_id,
                MaterialModel.user_id == user_id,
                MaterialModel.trashed_at.is_(None),
            )
        ).one_or_none()
        if row is None:
            return False
        filename, revision = row
        return (
            revision == 0 and filename is not None and filename.lower().endswith((".pdf", ".pptx"))
        )

    def material_state(self, user_id: UUID, source_id: UUID) -> str | None:
        return self.database.scalar(
            select(MaterialModel.status).where(
                MaterialModel.id == source_id,
                MaterialModel.user_id == user_id,
                MaterialModel.trashed_at.is_(None),
                MaterialModel.kind == "file",
            )
        )

    def identity(self, user_id: UUID, source: str, source_id: UUID) -> tuple[int, str] | None:
        model = PageModel if source == "page" else MaterialModel
        statement = select(model.version, model.title).where(
            model.id == source_id, model.user_id == user_id, model.trashed_at.is_(None)
        )
        if source == "material":
            statement = statement.where(
                MaterialModel.status == "ready", MaterialModel.kind == "file"
            )
        row = self.database.execute(statement).one_or_none()
        return (row[0], row[1]) if row else None

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
