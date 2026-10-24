import json
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from pydantic import JsonValue

from app.modules.ai.application.source_queries import (
    CalendarRead,
    DatabaseList,
    DatabaseRead,
    DatabaseReadQuery,
    MaterialRead,
    PageRead,
    ReadQuery,
    SearchRead,
)
from app.modules.calendar.application.composition import CalendarCompositionService
from app.modules.calendar.application.record_dates import RecordDateProjection
from app.modules.materials.application.excerpts import MaterialExcerptService
from app.modules.notes.application.service import NoteService
from app.modules.notes.domain.blocks import PageDocument, document_markdown
from app.modules.notes.domain.pages import PageNotFound
from app.modules.search.application.evidence import EvidenceResult, SourceReference
from app.modules.search.application.service import SearchService
from app.modules.search.domain.search import SearchQuery
from app.modules.workspace.application.database_views import DatabaseViewService


class SourceReader(Protocol):
    def read(self, user_id: UUID, query: ReadQuery) -> EvidenceResult: ...
    def context(self, user_id: UUID) -> str: ...


def json_value(value: object) -> JsonValue:
    return json.loads(json.dumps(value, default=str, ensure_ascii=False))


class WorkspaceSourceService:
    """Read-only composition over normal services in a single caller-owned snapshot."""

    def __init__(
        self,
        notes: NoteService,
        search: SearchService,
        materials: MaterialExcerptService,
        views: DatabaseViewService,
        calendar: CalendarCompositionService,
    ) -> None:
        self.notes, self.search, self.materials = notes, search, materials
        self.views, self.calendar = views, calendar

    def read(self, user_id: UUID, query: ReadQuery) -> EvidenceResult:
        if isinstance(query, SearchRead):
            hits = self.search.search(
                user_id,
                SearchQuery(
                    text=query.query,
                    source=query.source,
                    limit=query.limit,
                    offset=query.offset,
                    source_ids=query.source_ids,
                ),
            )
            return EvidenceResult(
                data=json_value(
                    [
                        {
                            "snippet": item.snippet,
                            "source": item.source,
                            "id": item.id,
                            "title": item.title,
                        }
                        for item in hits
                    ]
                ),
                sources=tuple(
                    SourceReference(
                        source=item.source,
                        id=str(item.id),
                        version=item.version,
                        title=item.title,
                        locator="search_snippet",
                    )
                    for item in hits
                ),
                coverage="partial",
                warnings=("lexical_search_only", "snippets_are_not_full_sources"),
                next_offset=query.offset + len(hits) if len(hits) == query.limit else None,
            )
        if isinstance(query, PageRead):
            page = self.notes.get(user_id, query.page_id, active=True)
            document = page.document
            if query.block_id is not None:
                blocks = tuple(block for block in document.blocks if block.id == query.block_id)
                if not blocks:
                    raise PageNotFound()
                document = PageDocument(blocks)
            text = document_markdown(document)
            end = min(query.offset + query.limit, len(text))
            return EvidenceResult(
                data=json_value(
                    {
                        "text": text[query.offset : end],
                        "total_characters": len(text),
                        "block_ids": [str(block.id) for block in document.blocks][:100],
                    }
                ),
                sources=(
                    SourceReference(
                        source="page",
                        id=str(page.id),
                        version=page.version,
                        title=page.title,
                        locator=(
                            f"markdown:{query.block_id or 'document'}:chars:{query.offset}:{end}"
                        ),
                    ),
                ),
                coverage="complete" if query.offset == 0 and end == len(text) else "partial",
                next_offset=end if end < len(text) else None,
                warnings=("selected_block_only",) if query.block_id else (),
            )
        if isinstance(query, MaterialRead):
            excerpt = self.materials.read(user_id, query.material_id, query.offset, query.limit)
            if excerpt is None:
                return EvidenceResult(
                    status="not_ready", warnings=("text_unavailable_or_not_extracted",)
                )
            end = excerpt.offset + len(excerpt.text)
            return EvidenceResult(
                data={"text": excerpt.text, "total_characters": excerpt.total_characters},
                sources=(
                    SourceReference(
                        source="material",
                        id=str(excerpt.material_id),
                        version=excerpt.version,
                        title=excerpt.title,
                        locator=f"extracted:chars:{query.offset}:{end}",
                    ),
                ),
                coverage="complete"
                if query.offset == 0 and end == excerpt.total_characters
                else "partial",
                warnings=("extracted_text_only_no_ocr",),
                next_offset=end if end < excerpt.total_characters else None,
            )
        if isinstance(query, DatabaseList):
            databases = self.views.databases.list(user_id, limit=query.limit, offset=query.offset)
            return EvidenceResult(
                data=json_value(
                    [
                        {"id": item.id, "name": item.name, "schema_version": item.schema_version}
                        for item in databases
                    ]
                ),
                sources=tuple(
                    SourceReference(
                        source="database", id=str(item.id), version=item.version, title=item.name
                    )
                    for item in databases
                ),
                coverage="partial" if query.offset or len(databases) == query.limit else "complete",
                next_offset=query.offset + len(databases)
                if len(databases) == query.limit
                else None,
            )
        if isinstance(query, DatabaseRead):
            database, properties = self.views.content.schema(user_id, query.database_id)
            views = self.views.list(user_id, database.id, limit=200)
            return EvidenceResult(
                data=json_value(
                    {
                        "schema_version": database.schema_version,
                        "properties": [
                            {
                                "id": item.id,
                                "name": item.name,
                                "kind": item.kind,
                                "options": [asdict(option) for option in item.options],
                            }
                            for item in properties
                            if item.trashed_at is None
                        ],
                        "views": [
                            {
                                "id": view.id,
                                "name": view.name,
                                "layout": view.layout,
                                "version": view.version,
                            }
                            for view in views
                        ],
                    }
                ),
                sources=(
                    SourceReference(
                        source="database",
                        id=str(database.id),
                        version=database.version,
                        title=database.name,
                        locator=f"schema:{database.schema_version}",
                    ),
                ),
                coverage="partial" if len(views) == 200 else "complete",
            )
        if isinstance(query, DatabaseReadQuery):
            if query.view_id is not None:
                if query.filters or query.sorts or query.columns is not None:
                    return EvidenceResult(
                        status="invalid", warnings=("saved_view_query_is_immutable",)
                    )
                result = self.views.table(
                    user_id, query.database_id, query.view_id, query.limit, query.offset
                )
            else:
                value = query.model_dump(mode="json", include={"filters", "sorts", "columns"})
                result = self.views.query(
                    user_id, query.database_id, value, query.limit, query.offset
                )
            return EvidenceResult(
                data=json_value(
                    {
                        "schema_version": result.schema_version,
                        "total": result.total,
                        "properties": [
                            {"id": item.id, "name": item.name, "kind": item.kind}
                            for item in result.properties
                        ],
                        "records": [
                            {
                                "id": item.record.id,
                                "page_id": item.page.id,
                                "title": item.page.title,
                                "values": item.record.values,
                                "page_version": item.page.version,
                            }
                            for item in result.items
                        ],
                    }
                ),
                sources=tuple(
                    SourceReference(
                        source="database_record",
                        id=str(item.record.id),
                        version=item.record.version,
                        title=item.page.title,
                        parent_id=str(query.database_id),
                        locator=f"schema:{result.schema_version}:page:{item.page.version}",
                    )
                    for item in result.items
                ),
                coverage="complete"
                if query.offset == 0 and len(result.items) == result.total
                else "partial",
                next_offset=query.offset + len(result.items)
                if query.offset + len(result.items) < result.total
                else None,
            )
        if isinstance(query, CalendarRead):
            warnings: list[str] = []
            selected = query.database_view_ids
            if selected is None:
                databases = self.views.databases.list(user_id, limit=200)
                selected_views = []
                if len(databases) == 200:
                    warnings.append("database_discovery_partial")
                for database in databases:
                    views = self.views.list(user_id, database.id, limit=200)
                    if len(views) == 200:
                        warnings.append("calendar_view_discovery_partial")
                    selected_views.extend(view.id for view in views if view.layout == "calendar")
                    if len(selected_views) > 20:
                        warnings.append("calendar_view_discovery_partial")
                        break
                selected = tuple(selected_views[:20])
            result = self.calendar.display(
                user_id,
                query.date_from,
                query.date_to,
                selected,
                include_hidden=query.include_hidden,
            )
            entries = [
                item
                for item in result.entries
                if query.include_hidden or not getattr(item, "skipped", False)
            ]
            batch = entries[query.offset : query.offset + query.limit]
            refs = tuple(
                SourceReference(
                    source=item.source,
                    id=(
                        f"{item.record_id}:{item.property_id}"
                        if isinstance(item, RecordDateProjection)
                        else str(item.source_event_id)
                    ),
                    version=item.record_version
                    if isinstance(item, RecordDateProjection)
                    else item.version,
                    title=item.title,
                    locator=f"dates:{query.date_from}:{query.date_to}",
                    parent_id=str(item.database_id)
                    if isinstance(item, RecordDateProjection)
                    else None,
                )
                for item in batch
            )
            return EvidenceResult(
                data=json_value(
                    {
                        "timezone": result.timezone,
                        "entries": [asdict(item) for item in batch],
                        "checked_at": datetime.now(UTC),
                        "source_state": asdict(result.source) if result.source else None,
                    }
                ),
                sources=refs,
                warnings=tuple(
                    dict.fromkeys(
                        [*result.warnings, *warnings, "calendar_display_is_not_availability"]
                    )
                ),
                coverage="partial"
                if warnings or query.offset or len(batch) < len(entries)
                else "complete",
                next_offset=query.offset + len(batch)
                if query.offset + len(batch) < len(entries)
                else None,
            )
        return EvidenceResult(status="invalid")
