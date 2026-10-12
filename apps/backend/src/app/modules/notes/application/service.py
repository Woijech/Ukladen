from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.modules.notes.application.ports import PageRepository
from app.modules.notes.domain.blocks import (
    is_markdown_document,
    markdown_document,
    parse_document,
    replace_markdown,
)
from app.modules.notes.domain.pages import (
    InvalidPageInput,
    Page,
    PageConflict,
    PageMetadata,
    PageNotFound,
    page_title,
    require_version,
)
from app.modules.users.application.ports import UserAuthentication
from app.modules.users.domain.profile import ProfileUnavailable


class NoteService:
    def __init__(
        self,
        repository: PageRepository,
        users: UserAuthentication,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.repository, self.users, self.now = repository, users, now

    def require_user(self, user_id: UUID, *, write: bool = False) -> None:
        # shortcut: serialize owner writes; use finer locks if per-user throughput requires it.
        active = self.users.lock_active(user_id) if write else self.users.is_active(user_id)
        if not active:
            raise ProfileUnavailable()

    def get(self, user_id: UUID, page_id: UUID, *, active: bool = False) -> Page:
        self.require_user(user_id)
        page = self.repository.get(user_id, page_id)
        if page is None:
            raise PageNotFound()
        if active and page.trashed_at is not None:
            raise PageConflict()
        return page

    def summary(self, user_id: UUID, page_id: UUID, *, active: bool = False) -> PageMetadata:
        self.require_user(user_id)
        page = self.repository.summary(user_id, page_id)
        if page is None:
            raise PageNotFound()
        if active and page.trashed_at is not None:
            raise PageConflict()
        return page

    def list_pages(
        self,
        user_id: UUID,
        *,
        parent_id: UUID | None = None,
        roots_only: bool = False,
        trashed: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PageMetadata]:
        self.require_user(user_id)
        if not 1 <= limit <= 200 or not 0 <= offset <= 2**31 - 1 or (parent_id and roots_only):
            raise InvalidPageInput()
        if parent_id is not None:
            self.summary(user_id, parent_id)
        return self.repository.list_pages(user_id, parent_id, roots_only, trashed, limit, offset)

    def _parent(self, user_id: UUID, parent_id: UUID | None, page_id: UUID | None = None) -> None:
        seen: set[UUID] = set()
        while parent_id is not None:
            if not isinstance(parent_id, UUID):
                raise InvalidPageInput()
            if parent_id == page_id or parent_id in seen:
                raise PageConflict()
            seen.add(parent_id)
            parent_id = self.summary(user_id, parent_id, active=True).parent_id

    def create(
        self,
        user_id: UUID,
        title: str,
        content: str = "",
        parent_id: UUID | None = None,
        *,
        document: Mapping[str, object] | None = None,
    ) -> Page:
        self.require_user(user_id, write=True)
        title = page_title(title)
        if document is not None and content != "":
            raise InvalidPageInput()
        identifier = uuid4()
        body = (
            parse_document(document)
            if document is not None
            else markdown_document(content, block_id=identifier)
        )
        self._parent(user_id, parent_id)
        now = self.now()
        page = Page(
            id=identifier,
            user_id=user_id,
            parent_id=parent_id,
            title=title,
            document=body,
            version=1,
            created_at=now,
            updated_at=now,
        )
        self.repository.create(page)
        return page

    def update(
        self,
        user_id: UUID,
        page_id: UUID,
        changes: Mapping[str, object],
        expected_version: int,
    ) -> Page:
        self.require_user(user_id, write=True)
        page = self.get(user_id, page_id, active=True)
        require_version(page.version, expected_version)
        if not changes or changes.keys() - {"title", "content", "parent_id"}:
            raise InvalidPageInput()
        title = page_title(changes.get("title", page.title))
        body = page.document
        if "content" in changes:
            if not is_markdown_document(body):
                raise PageConflict()
            content = changes["content"]
            if not isinstance(content, str):
                raise InvalidPageInput()
            body = replace_markdown(body, content, block_id=page.id)
        parent = changes.get("parent_id", page.parent_id)
        if parent is not None and not isinstance(parent, UUID):
            raise InvalidPageInput()
        self._parent(user_id, parent, page.id)
        updated = replace(
            page,
            title=title,
            document=body,
            parent_id=parent,
            version=page.version + 1,
            updated_at=self.now(),
        )
        self.repository.save(updated, expected_version)
        return updated

    def trash(self, user_id: UUID, page_id: UUID, expected_version: int) -> Page:
        self.require_user(user_id, write=True)
        page = self.get(user_id, page_id, active=True)
        require_version(page.version, expected_version)
        self.repository.trash_branch(user_id, page_id, self.now())
        return self.get(user_id, page_id)

    def restore(self, user_id: UUID, page_id: UUID, expected_version: int) -> Page:
        self.require_user(user_id, write=True)
        page = self.get(user_id, page_id)
        require_version(page.version, expected_version)
        if page.trashed_at is None or page.trash_batch_id != page.id:
            raise PageConflict()
        self._parent(user_id, page.parent_id, page.id)
        self.repository.restore_batch(user_id, page.id, self.now())
        return self.get(user_id, page_id)

    def replace_document(
        self,
        user_id: UUID,
        page_id: UUID,
        document: Mapping[str, object],
        expected_version: int,
    ) -> Page:
        self.require_user(user_id, write=True)
        page = self.get(user_id, page_id, active=True)
        require_version(page.version, expected_version)
        updated = replace(
            page, document=parse_document(document), version=page.version + 1, updated_at=self.now()
        )
        self.repository.save(updated, expected_version)
        return updated
