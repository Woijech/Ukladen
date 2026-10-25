from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Connection
from sqlalchemy.orm import sessionmaker
from test_auth_persistence import database_connection as database_connection
from test_auth_persistence import migration_config
from test_auth_sessions import concurrent_engine as concurrent_engine

from alembic import command
from app.modules.ai.application.source_queries import SearchRead
from app.modules.notes.domain.blocks import document_value, markdown_document
from app.modules.notes.infrastructure.orm import PageModel
from app.modules.search.application.chunking import chunks
from app.modules.search.application.embeddings import EmbeddingProfile
from app.modules.search.application.indexing import IndexingService
from app.modules.search.domain.chunks import SourceDocument, checked_vector
from app.modules.search.infrastructure.hybrid import HybridSearch
from app.modules.search.infrastructure.indexing import SqlAlchemyIndexStore
from app.modules.users.infrastructure.orm import UserModel


class Embeddings:
    profile = EmbeddingProfile("fake", "topics", "v1", 384, 512, True)

    def embed(self, texts, *, purpose):
        return [
            tuple(
                [
                    1.0 if "database" in text or "нормализ" in text.lower() else 0.0,
                    0.0 if "database" in text or "нормализ" in text.lower() else 1.0,
                ]
                + [0.0] * 382
            )
            for text in texts
        ]


def test_chunking_covers_unicode_without_truncation_and_preserves_locations():
    body = "Базы данных. " * 200
    document = SourceDocument(
        uuid4(), "page", uuid4(), 1, "Lecture", body, ((0, len(body), "block:one"),)
    )
    result = list(chunks(document, lambda text: len(text) + 4))
    assert result[0].start == 0 and result[-1].end == len(body)
    assert all(
        len(item.text) + 4 <= 384 and item.text == body[item.start : item.end] for item in result
    )
    assert all(left.end >= right.start for left, right in zip(result, result[1:], strict=False))
    assert all(item.locator.startswith("block:one;") for item in result)
    with pytest.raises(ValueError):
        checked_vector([float("nan")] * 384, 384)


def test_index_claim_fencing_current_sources_and_hybrid(concurrent_engine):
    owner, other, page = uuid4(), uuid4(), uuid4()
    sessions = sessionmaker(concurrent_engine, expire_on_commit=False)
    with sessions.begin() as database:
        database.add_all(
            [
                UserModel(id=owner, email="semantic-owner@example.com"),
                UserModel(id=other, email="semantic-other@example.com"),
            ]
        )
        database.flush()
        database.add(
            PageModel(
                id=page,
                user_id=owner,
                title="Lecture",
                document=document_value(markdown_document("database normalization")),
            )
        )
    provider = Embeddings()
    store = SqlAlchemyIndexStore(sessions, provider.profile)
    store.register()
    assert (owner, "page", page) in store.candidates()
    work = store.claim(owner, "page", page)
    assert work is not None and store.claim(owner, "page", page) is None
    assert store.claim(other, "page", page) is None
    batch = tuple(chunks(work.document, len))
    assert store.publish(
        work, 0, batch, provider.embed([item.text for item in batch], purpose="document")
    )
    assert store.finish(work)
    result = HybridSearch(sessions, provider).read(owner, SearchRead(query="нормализация"))
    assert result.sources[0].id == str(page)
    assert result.sources[0].locator.startswith("block:")
    assert (
        HybridSearch(sessions, provider).read(other, SearchRead(query="нормализация")).sources == ()
    )
    with sessions.begin() as database:
        row = database.get(PageModel, page)
        assert row is not None
        row.version += 1
        row.document = document_value(markdown_document("updated lecture"))
    assert (
        not HybridSearch(sessions, provider).read(owner, SearchRead(query="нормализация")).sources
    )
    assert not store.publish(
        work, 0, batch, provider.embed([item.text for item in batch], purpose="document")
    )
    IndexingService(store, provider, len).process(owner, "page", page)
    with sessions.begin() as database:
        row = database.get(PageModel, page)
        assert row is not None
        row.trashed_at, row.trash_batch_id = datetime.now(UTC), uuid4()
    assert HybridSearch(sessions, provider).read(owner, SearchRead(query="updated")).sources == ()


def test_expired_index_claim_cannot_publish_after_recovery(concurrent_engine):
    owner, page = uuid4(), uuid4()
    sessions = sessionmaker(concurrent_engine, expire_on_commit=False)
    with sessions.begin() as database:
        database.add(UserModel(id=owner, email="semantic-recovery@example.com"))
        database.flush()
        database.add(
            PageModel(
                id=page,
                user_id=owner,
                title="Recovery",
                document=document_value(markdown_document("database")),
            )
        )
    now = datetime.now(UTC)
    store = SqlAlchemyIndexStore(sessions, Embeddings.profile, now=lambda: now)
    store.register()
    first = store.claim(owner, "page", page)
    now += timedelta(minutes=3)
    second = store.claim(owner, "page", page)
    assert first and second and first.lease != second.lease
    assert not store.finish(first)
    assert store.finish(second)


def test_semantic_migrations_match_metadata(database_connection: Connection):
    command.check(migration_config(database_connection))
    command.downgrade(migration_config(database_connection), "0028_material_locations")
    command.upgrade(migration_config(database_connection), "head")
    command.check(migration_config(database_connection))


def test_embedding_replacement_keeps_generations_separate_and_lexical_fallback(concurrent_engine):
    from dataclasses import replace
    from unittest.mock import patch

    from sqlalchemy import select

    from app.modules.search.infrastructure.index_models import SearchChunkModel

    owner, page = uuid4(), uuid4()
    sessions = sessionmaker(concurrent_engine, expire_on_commit=False)
    with sessions.begin() as database:
        database.add(UserModel(id=owner, email="generation-replacement@example.com"))
        database.flush()
        database.add(
            PageModel(
                id=page,
                user_id=owner,
                title="Synthetic lecture",
                document=document_value(markdown_document("database normalization")),
            )
        )
    original = Embeddings()
    original_store = SqlAlchemyIndexStore(sessions, original.profile)
    original_store.register()
    IndexingService(original_store, original, len).process(owner, "page", page)
    query = SearchRead(query="semantic-only-query-without-a-lexical-match")
    assert HybridSearch(sessions, original).read(owner, query).sources

    replacement = Embeddings()
    replacement.profile = replace(original.profile, model="different-topics", revision="v2")
    replacement_store = SqlAlchemyIndexStore(sessions, replacement.profile)
    replacement_store.register()
    assert replacement_store.generation != original_store.generation
    pending = HybridSearch(sessions, replacement).read(owner, query)
    assert not pending.sources and "index_pending_or_unavailable" in pending.warnings
    assert HybridSearch(sessions, original).read(owner, query).sources
    IndexingService(replacement_store, replacement, len).process(owner, "page", page)
    assert HybridSearch(sessions, replacement).read(owner, query).sources[0].id == str(page)
    with sessions() as database:
        assert set(database.scalars(select(SearchChunkModel.generation))) == {
            original_store.generation,
            replacement_store.generation,
        }
    with patch.object(
        replacement, "embed", side_effect=RuntimeError("Synthetic inference failure")
    ):
        result = HybridSearch(sessions, replacement).read(owner, SearchRead(query="normalization"))
    assert result.sources[0].id == str(page)
    assert "semantic_unavailable_lexical_fallback" in result.warnings
