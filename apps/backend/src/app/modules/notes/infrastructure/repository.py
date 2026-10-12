from dataclasses import asdict
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session, defer

from app.modules.notes.domain.blocks import document_value, parse_document
from app.modules.notes.domain.pages import Page, PageConflict, PageMetadata
from app.modules.notes.infrastructure.orm import PageModel


def page_metadata(row: PageModel) -> PageMetadata:
    return PageMetadata(
        **{field: getattr(row, field) for field in PageMetadata.__dataclass_fields__}
    )


def page_entity(row: PageModel) -> Page:
    return Page(**asdict(page_metadata(row)), document=parse_document(row.document))


def page_values(page: Page) -> dict[str, object]:
    values: dict[str, object] = asdict(page)
    values["document"] = document_value(page.document)
    return values


class SqlAlchemyPageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, user_id: UUID, page_id: UUID) -> Page | None:
        row = self.session.scalar(
            select(PageModel)
            .where(PageModel.user_id == user_id, PageModel.id == page_id)
            .execution_options(populate_existing=True)
        )
        return page_entity(row) if row else None

    def summary(self, user_id: UUID, page_id: UUID) -> PageMetadata | None:
        row = self.session.scalar(
            select(PageModel)
            .options(defer(PageModel.document))
            .where(PageModel.user_id == user_id, PageModel.id == page_id)
            .execution_options(populate_existing=True)
        )
        return page_metadata(row) if row else None

    def list_pages(
        self,
        user_id: UUID,
        parent_id: UUID | None,
        roots_only: bool,
        trashed: bool,
        limit: int,
        offset: int,
    ) -> list[PageMetadata]:
        query = (
            select(PageModel)
            .options(defer(PageModel.document))
            .where(
                PageModel.user_id == user_id,
                PageModel.trashed_at.is_not(None) if trashed else PageModel.trashed_at.is_(None),
            )
        )
        if parent_id is not None or roots_only:
            query = query.where(PageModel.parent_id == parent_id)
        return [
            page_metadata(row)
            for row in self.session.scalars(
                query.order_by(PageModel.created_at, PageModel.id).limit(limit).offset(offset)
            )
        ]

    def create(self, page: Page) -> None:
        self.session.add(PageModel(**page_values(page)))
        self.session.flush()

    def save(self, page: Page, expected_version: int) -> None:
        values = page_values(page)
        values.pop("id")
        values.pop("user_id")
        row_id = self.session.scalar(
            update(PageModel)
            .where(
                PageModel.id == page.id,
                PageModel.user_id == page.user_id,
                PageModel.version == expected_version,
            )
            .values(**values)
            .returning(PageModel.id)
        )
        if row_id is None:
            raise PageConflict()

    def trash_branch(self, user_id: UUID, page_id: UUID, now: datetime) -> None:
        branch = (
            select(PageModel.id)
            .where(PageModel.user_id == user_id, PageModel.id == page_id)
            .cte("branch", recursive=True)
        )
        branch = branch.union_all(
            select(PageModel.id)
            .join(branch, PageModel.parent_id == branch.c.id)
            .where(PageModel.user_id == user_id)
        )
        self.session.execute(
            update(PageModel)
            .where(
                PageModel.user_id == user_id,
                PageModel.id.in_(select(branch.c.id)),
                PageModel.trashed_at.is_(None),
            )
            .values(
                trashed_at=now,
                trash_batch_id=page_id,
                updated_at=now,
                version=PageModel.version + 1,
            )
            .execution_options(synchronize_session=False)
        )

    def restore_batch(self, user_id: UUID, batch_id: UUID, now: datetime) -> None:
        self.session.execute(
            update(PageModel)
            .where(
                PageModel.user_id == user_id,
                PageModel.trash_batch_id == batch_id,
            )
            .values(
                trashed_at=None, trash_batch_id=None, updated_at=now, version=PageModel.version + 1
            )
            .execution_options(synchronize_session=False)
        )
