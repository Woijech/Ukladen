"""Owner-scoped, atomic copy import using existing application services."""

import ast
import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, replace
from typing import Protocol
from uuid import UUID, uuid4

from app.modules.notes.domain.blocks import (
    Block,
    DatabaseViewBlock,
    ToggleBlock,
    document_value,
    parse_document,
)
from app.modules.notes.domain.pages import page_title
from app.modules.workspace.application.database_views import DatabaseViewService
from app.modules.workspace.domain.database_views import parse_query, query_value
from app.modules.workspace.domain.formulas import formula_tree
from app.modules.workspace.domain.transfer import (
    MAX_ARCHIVE_BYTES,
    MAX_DATABASES,
    MAX_PAGES,
    MAX_RECORDS,
    MAX_VIEWS,
    DatabaseSnapshot,
    InvalidTransfer,
    PageSnapshot,
    PropertySnapshot,
    RecordSnapshot,
    ViewSnapshot,
    WorkspaceArchive,
)


def encoded(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            default=str,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except ValueError, TypeError, UnicodeError, RecursionError:
        raise InvalidTransfer("Invalid portable JSON data.") from None


def collect[T](
    fetch: Callable[[int, int], list[T]],
    maximum: int,
    on_item: Callable[[T], None] | None = None,
) -> list[T]:
    result: list[T] = []
    while True:
        batch = fetch(200, len(result))
        if on_item is not None:
            for item in batch:
                on_item(item)
        result.extend(batch)
        if len(result) > maximum:
            raise InvalidTransfer("Transfer limit exceeded. Use the full backup instead.")
        if len(batch) < 200:
            return result


def page_order(archive: WorkspaceArchive) -> list[PageSnapshot]:
    if (
        archive.format != "ukladen.pages-databases"
        or type(archive.version) is not int
        or archive.version != 1
    ):
        raise InvalidTransfer("Unsupported archive format or version.")
    if (
        len(archive.pages) > MAX_PAGES
        or len(archive.databases) > MAX_DATABASES
        or sum(len(db.records) for db in archive.databases) > MAX_RECORDS
        or sum(len(db.views) for db in archive.databases) > MAX_VIEWS
        or any(len(db.properties) > 100 for db in archive.databases)
        or len(encoded(asdict(archive))) > MAX_ARCHIVE_BYTES
    ):
        raise InvalidTransfer("Transfer limit exceeded. Use the full backup instead.")
    identifiers = [p.id for p in archive.pages]
    for db in archive.databases:
        identifiers.extend(
            [
                db.id,
                *(p.id for p in db.properties),
                *(r.id for r in db.records),
                *(v.id for v in db.views),
            ]
        )
    if len(set(identifiers)) != len(identifiers):
        raise InvalidTransfer("Duplicate object identities in archive.")
    pages = {p.id: p for p in archive.pages}
    children: dict[UUID | None, list[PageSnapshot]] = {}
    for page in archive.pages:
        if page.parent_id is not None and page.parent_id not in pages:
            raise InvalidTransfer("Missing parent page in archive.")
        children.setdefault(page.parent_id, []).append(page)
    result = list(children.get(None, []))
    depths = {p.id: 0 for p in result}
    for page in result:
        if depths[page.id] >= 64:
            raise InvalidTransfer("Page hierarchy exceeds 64 levels.")
        for child in children.get(page.id, []):
            depths[child.id] = depths[page.id] + 1
            result.append(child)
    if len(result) != len(pages):
        raise InvalidTransfer("Cyclic page hierarchy in archive.")
    for page in result:
        if page.trash_batch_id is not None:
            root = pages.get(page.trash_batch_id)
            if root is None or root.trash_batch_id != root.id:
                raise InvalidTransfer("Invalid page trash batch.")
            ancestor: UUID | None = page.id
            while ancestor != root.id and ancestor is not None:
                ancestor = pages[ancestor].parent_id
            if ancestor is None:
                raise InvalidTransfer("Trash batch root is not an ancestor.")
        elif page.parent_id and pages[page.parent_id].trash_batch_id is not None:
            raise InvalidTransfer("An active page has a trashed parent.")
    return result


class TransferReceipts(Protocol):
    def get(self, user_id: UUID, digest: str) -> UUID | None: ...
    def save(self, user_id: UUID, digest: str, root_page_id: UUID) -> None: ...


class WorkspaceTransfer:
    def __init__(
        self, views: DatabaseViewService, receipts: TransferReceipts | None = None
    ) -> None:
        self.views, self.content = views, views.content
        self.databases, self.notes = views.databases, views.notes
        self.receipts = receipts

    def apply(self, user_id: UUID, archive: WorkspaceArchive, title: str) -> UUID:
        if self.receipts is None:
            raise RuntimeError("Import receipt storage is required.")
        self.notes.require_user(user_id, write=True)
        digest = self.digest(user_id, archive, title)
        previous = self.receipts.get(user_id, digest)
        if previous is not None:
            return previous
        root = self.copy(user_id, archive, title)
        self.receipts.save(user_id, digest, root)
        return root

    def export(self, user_id: UUID) -> WorkspaceArchive:
        self.notes.require_user(user_id)
        pages: list[PageSnapshot] = []
        databases: list[DatabaseSnapshot] = []
        used = 0

        def charge(
            value: PageSnapshot
            | DatabaseSnapshot
            | PropertySnapshot
            | RecordSnapshot
            | ViewSnapshot,
        ) -> None:
            nonlocal used
            used += len(encoded(asdict(value)))
            if used > MAX_ARCHIVE_BYTES:
                raise InvalidTransfer("Transfer exceeds 32 MiB. Use the full backup instead.")

        for trashed in (False, True):
            summaries = collect(
                lambda limit, offset, trashed=trashed: self.notes.list_pages(
                    user_id, trashed=trashed, limit=limit, offset=offset
                ),
                MAX_PAGES - len(pages),
            )
            for summary in summaries:
                page = self.notes.get(user_id, summary.id)
                snapshot = PageSnapshot(
                    id=page.id,
                    parent_id=page.parent_id,
                    title=page.title,
                    document=document_value(page.document),
                    trash_batch_id=page.trash_batch_id,
                )
                charge(snapshot)
                pages.append(snapshot)
        record_count = view_count = 0
        for trashed in (False, True):
            definitions = collect(
                lambda limit, offset, trashed=trashed: self.databases.list(
                    user_id, trashed, limit, offset
                ),
                MAX_DATABASES - len(databases),
            )
            for db in definitions:
                properties = tuple(
                    PropertySnapshot(
                        id=p.id,
                        name=p.name,
                        kind=p.kind,
                        options=tuple({"id": str(o.id), "name": o.name} for o in p.options),
                        relation_database_id=p.relation_database_id,
                        calculation=p.calculation,
                        position=p.position,
                        trashed=p.trashed_at is not None,
                    )
                    for p in self.content.repository.properties(user_id, db.id)
                )
                for prop in properties:
                    charge(prop)
                records: list[RecordSnapshot] = []
                for state in (False, True):
                    rows = collect(
                        lambda limit, offset, db=db, state=state: (
                            self.content.repository.list_records(
                                user_id, db.id, state, limit, offset
                            )
                        ),
                        MAX_RECORDS - record_count,
                        on_item=lambda r: charge(
                            RecordSnapshot(
                                id=r.id,
                                page_id=r.page_id,
                                values=dict(r.values),
                                trashed=r.trashed_at is not None,
                            )
                        ),
                    )
                    record_count += len(rows)
                    records.extend(
                        RecordSnapshot(
                            id=r.id,
                            page_id=r.page_id,
                            values=dict(r.values),
                            trashed=r.trashed_at is not None,
                        )
                        for r in rows
                    )
                saved = collect(
                    lambda limit, offset, db=db: self.views.repository.list(
                        user_id, db.id, limit, offset
                    ),
                    MAX_VIEWS - view_count,
                    on_item=lambda v: charge(
                        ViewSnapshot(
                            id=v.id,
                            name=v.name,
                            color=v.color,
                            query=query_value(v.query),
                            layout=v.layout,
                            date_property_id=v.date_property_id,
                            calendar_layout=v.calendar_layout,
                        )
                    ),
                )
                view_count += len(saved)
                snapshot = DatabaseSnapshot(
                    id=db.id,
                    name=db.name,
                    color=db.color,
                    trashed=db.trashed_at is not None,
                    properties=properties,
                    records=tuple(records),
                    views=tuple(
                        ViewSnapshot(
                            id=v.id,
                            name=v.name,
                            color=v.color,
                            query=query_value(v.query),
                            layout=v.layout,
                            date_property_id=v.date_property_id,
                            calendar_layout=v.calendar_layout,
                        )
                        for v in saved
                    ),
                )
                charge(replace(snapshot, properties=(), records=(), views=()))
                databases.append(snapshot)
        archive = WorkspaceArchive(
            format="ukladen.pages-databases",
            version=1,
            pages=tuple(pages),
            databases=tuple(databases),
        )
        page_order(archive)
        return archive

    @staticmethod
    def digest(user_id: UUID, archive: WorkspaceArchive, title: str) -> str:
        page_order(archive)
        return hashlib.sha256(
            encoded({"owner": str(user_id), "title": page_title(title), "archive": asdict(archive)})
        ).hexdigest()

    def copy(self, user_id: UUID, archive: WorkspaceArchive, title: str) -> UUID:
        ordered = page_order(archive)
        self.notes.require_user(user_id, write=True)
        title = page_title(title)
        db_ids: dict[UUID, UUID] = {}
        prop_ids: dict[UUID, UUID] = {}
        view_ids: dict[UUID, UUID] = {}
        record_ids: dict[UUID, UUID] = {}
        schema: dict[UUID, int] = {}
        for db in archive.databases:
            created = self.databases.create(user_id, db.name, db.color)
            db_ids[db.id], schema[db.id] = created.id, created.schema_version

        def mapped(mapping: dict[UUID, UUID], identifier: UUID) -> UUID:
            if identifier not in mapping:
                raise InvalidTransfer("An archive reference is missing or unavailable.")
            return mapping[identifier]

        rank = {"relation": 1, "formula": 2, "rollup": 3}
        properties = [(db, p) for db in archive.databases for p in db.properties]
        for db, prop in sorted(properties, key=lambda pair: rank.get(pair[1].kind, 0)):
            calculation = dict(prop.calculation)
            if prop.kind == "formula":
                tree, _ = formula_tree(calculation.get("expression"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        argument = node.args[0]
                        assert isinstance(argument, ast.Constant)
                        argument.value = str(mapped(prop_ids, UUID(str(argument.value))))
                calculation["expression"] = ast.unparse(tree)
            if prop.kind == "rollup":
                for key in ("relation_property_id", "value_property_id"):
                    if key in calculation:
                        calculation[key] = str(mapped(prop_ids, UUID(calculation[key])))
            created = self.content.create_property(
                user_id,
                db_ids[db.id],
                schema[db.id],
                prop.name,
                prop.kind,
                prop.options,
                mapped(db_ids, prop.relation_database_id) if prop.relation_database_id else None,
                calculation,
            )
            prop_ids[prop.id] = created.property.id
            updated = self.content.update_property(
                user_id,
                db_ids[db.id],
                created.property.id,
                created.property.version,
                created.schema_version,
                {"position": prop.position},
            )
            schema[db.id] = updated.schema_version
        for db in archive.databases:
            for view in db.views:
                query = parse_query(view.query)
                query = replace(
                    query,
                    columns=tuple(mapped(prop_ids, p) for p in query.columns)
                    if query.columns is not None
                    else None,
                    filters=tuple(
                        replace(f, property_id=mapped(prop_ids, f.property_id))
                        for f in query.filters
                    ),
                    sorts=tuple(
                        replace(s, property_id=mapped(prop_ids, s.property_id)) for s in query.sorts
                    ),
                    group_by=mapped(prop_ids, query.group_by) if query.group_by else None,
                )
                created_view = self.views.create(
                    user_id,
                    db_ids[db.id],
                    schema[db.id],
                    view.name,
                    view.color,
                    query_value(query),
                    view.layout,
                    mapped(prop_ids, view.date_property_id) if view.date_property_id else None,
                    view.calendar_layout,
                )
                view_ids[view.id] = created_view.id
        root = self.notes.create(user_id, title)
        page_ids: dict[UUID, UUID] = {}
        for page in ordered:
            created_page = self.notes.create(
                user_id,
                page.title,
                parent_id=(mapped(page_ids, page.parent_id) if page.parent_id else root.id),
            )
            page_ids[page.id] = created_page.id

        def block_copy(block: Block) -> Block:
            if isinstance(block, ToggleBlock):
                return replace(block, id=uuid4(), children=tuple(map(block_copy, block.children)))
            if isinstance(block, DatabaseViewBlock):
                return replace(
                    block,
                    id=uuid4(),
                    database_id=mapped(db_ids, block.database_id),
                    view_id=mapped(view_ids, block.view_id),
                )
            return replace(block, id=uuid4())

        for page in ordered:
            body = parse_document(page.document)
            body = replace(body, blocks=tuple(map(block_copy, body.blocks)))
            self.notes.replace_document(user_id, page_ids[page.id], document_value(body), 1)
        for db in archive.databases:
            relation_ids = {p.id for p in db.properties if p.kind == "relation"}
            for record in db.records:
                values = {
                    str(mapped(prop_ids, UUID(key))): value
                    for key, value in record.values.items()
                    if UUID(key) not in relation_ids
                }
                created_record = self.content.create_record(
                    user_id,
                    db_ids[db.id],
                    schema[db.id],
                    values,
                    page_id=mapped(page_ids, record.page_id),
                )
                record_ids[record.id] = created_record.record.id
        for db in archive.databases:
            relation_ids = {p.id for p in db.properties if p.kind == "relation"}
            for record in db.records:
                values: dict[str, object] = {}
                for key, value in record.values.items():
                    if UUID(key) in relation_ids:
                        if not isinstance(value, list) or any(
                            not isinstance(v, str) for v in value
                        ):
                            raise InvalidTransfer("Invalid relation values in archive.")
                        values[str(mapped(prop_ids, UUID(key)))] = [
                            str(mapped(record_ids, UUID(str(v)))) for v in value
                        ]
                if values:
                    self.content.update_record(
                        user_id, db_ids[db.id], record_ids[record.id], 1, schema[db.id], values
                    )
        for db in archive.databases:
            for record in db.records:
                if record.trashed:
                    current = self.content.record(user_id, db_ids[db.id], record_ids[record.id])
                    self.content.record_lifecycle(
                        user_id, db_ids[db.id], current.id, current.version
                    )
            for prop in db.properties:
                if prop.trashed:
                    current_property = self.content.definition(
                        self.content.repository.properties(user_id, db_ids[db.id]),
                        prop_ids[prop.id],
                    )
                    result = self.content.property_lifecycle(
                        user_id,
                        db_ids[db.id],
                        current_property.id,
                        current_property.version,
                        schema[db.id],
                    )
                    schema[db.id] = result.schema_version
        for page in reversed(ordered):
            if page.trash_batch_id == page.id:
                current_page = self.notes.get(user_id, page_ids[page.id])
                self.notes.trash(user_id, current_page.id, current_page.version)
        for page in ordered:
            expected = page_ids[page.trash_batch_id] if page.trash_batch_id else None
            if self.notes.get(user_id, page_ids[page.id]).trash_batch_id != expected:
                raise InvalidTransfer("Inconsistent page trash batches in archive.")
        for db in archive.databases:
            if db.trashed:
                current_db = self.databases.get(user_id, db_ids[db.id])
                self.databases.lifecycle(user_id, current_db.id, current_db.version)
        return root.id
