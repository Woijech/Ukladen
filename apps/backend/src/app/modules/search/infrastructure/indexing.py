import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, literal, or_, select, union_all
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from app.modules.materials.infrastructure.orm import MaterialModel
from app.modules.notes.infrastructure.orm import PageModel
from app.modules.search.application.chunking import CHUNKER_REVISION
from app.modules.search.application.embeddings import EmbeddingProfile
from app.modules.search.application.indexing import IndexWork
from app.modules.search.domain.chunks import TextChunk
from app.modules.search.infrastructure.index_models import (
    IndexGenerationModel,
    IndexSourceModel,
    SearchChunkModel,
)
from app.modules.search.infrastructure.orm import MaterialSearchDocumentModel
from app.modules.search.infrastructure.source_documents import SqlAlchemySourceDocuments
from app.modules.users.infrastructure.orm import UserModel
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication


def generation_profile(profile: EmbeddingProfile) -> tuple[str, dict]:
    data = asdict(profile) | {"chunker": CHUNKER_REVISION, "tokenizer_revision": profile.revision}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest(), data


class SqlAlchemyIndexStore:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        profile: EmbeddingProfile,
        *,
        now=lambda: datetime.now(UTC),
    ):
        self.sessions, self.now = sessions, now
        self.generation, self.profile = generation_profile(profile)

    def register(self) -> None:
        with self.sessions.begin() as database:
            database.execute(
                insert(IndexGenerationModel)
                .values(id=self.generation, profile=self.profile)
                .on_conflict_do_nothing()
            )

    def candidates(self, limit: int = 100) -> list[tuple[UUID, str, UUID]]:
        pages = select(
            PageModel.user_id.label("user_id"),
            literal("page").label("source"),
            PageModel.id.label("source_id"),
            PageModel.version.label("version"),
        ).where(PageModel.trashed_at.is_(None))
        materials = (
            select(
                MaterialModel.user_id, literal("material"), MaterialModel.id, MaterialModel.version
            )
            .join(
                MaterialSearchDocumentModel,
                MaterialSearchDocumentModel.material_id == MaterialModel.id,
            )
            .where(
                MaterialModel.trashed_at.is_(None),
                MaterialModel.status == "ready",
                MaterialModel.kind == "file",
            )
        )
        canonical = union_all(pages, materials).subquery()
        index = IndexSourceModel
        with self.sessions() as database:
            rows = database.execute(
                select(canonical.c.user_id, canonical.c.source, canonical.c.source_id)
                .join(
                    UserModel,
                    (UserModel.id == canonical.c.user_id) & (UserModel.status == "active"),
                )
                .outerjoin(
                    index,
                    and_(
                        index.user_id == canonical.c.user_id,
                        index.source == canonical.c.source,
                        index.source_id == canonical.c.source_id,
                        index.generation == self.generation,
                    ),
                )
                .where(
                    or_(
                        index.source_id.is_(None),
                        index.version != canonical.c.version,
                        and_(index.status.in_(["pending", "failed"]), index.attempts < 3),
                        and_(index.status == "processing", index.lease_until <= self.now()),
                    )
                )
                .order_by(canonical.c.user_id, canonical.c.source, canonical.c.source_id)
                .limit(limit)
            )
            return [(row[0], row[1], row[2]) for row in rows]

    def claim(self, user_id: UUID, source: str, source_id: UUID) -> IndexWork | None:
        with self.sessions.begin() as database:
            if not SqlAlchemyUserAuthentication(database).lock_active(user_id):
                return None
            document = SqlAlchemySourceDocuments(database).read(user_id, source, source_id)
            if document is None:
                return None
            key = (user_id, source, source_id, self.generation)
            row = database.get(IndexSourceModel, key, with_for_update=True)
            now = self.now()
            if row is None:
                row = IndexSourceModel(
                    user_id=user_id,
                    source=source,
                    source_id=source_id,
                    generation=self.generation,
                    version=document.version,
                    status="pending",
                    attempts=0,
                    updated_at=now,
                )
                database.add(row)
            elif row.version != document.version:
                row.version, row.status, row.attempts = document.version, "pending", 0
            elif row.status == "ready" or (
                row.status == "processing" and row.lease_until and row.lease_until > now
            ):
                return None
            if row.attempts >= 3:
                row.status, row.error = "failed", "indexing_failed"
                return None
            lease = uuid4()
            row.lease, row.lease_until = lease, now + timedelta(minutes=2)
            row.status, row.attempts, row.updated_at, row.error = (
                "processing",
                row.attempts + 1,
                now,
                None,
            )
            database.execute(
                delete(SearchChunkModel).where(
                    SearchChunkModel.user_id == user_id,
                    SearchChunkModel.source == source,
                    SearchChunkModel.source_id == source_id,
                    SearchChunkModel.generation == self.generation,
                )
            )
            assert row.lease is not None
            return IndexWork(document, self.generation, lease)

    def current(self, database: Session, work: IndexWork) -> IndexSourceModel | None:
        document = work.document
        if not SqlAlchemyUserAuthentication(database).lock_active(document.user_id):
            return None
        row = database.get(
            IndexSourceModel,
            (document.user_id, document.source, document.id, work.generation),
            with_for_update=True,
        )
        canonical = SqlAlchemySourceDocuments(database).read(
            document.user_id, document.source, document.id
        )
        if (
            row is None
            or row.lease != work.lease
            or row.status != "processing"
            or row.lease_until is None
            or row.lease_until <= self.now()
        ):
            return None
        if canonical is None or canonical.version != document.version:
            row.status, row.lease, row.lease_until = "pending", None, None
            return None
        return row

    def publish(
        self,
        work: IndexWork,
        start: int,
        batch: tuple[TextChunk, ...],
        vectors: list[tuple[float, ...]],
    ) -> bool:
        with self.sessions.begin() as database:
            row = self.current(database, work)
            if row is None:
                return False
            for number, (chunk, vector) in enumerate(zip(batch, vectors, strict=True), start):
                database.add(
                    SearchChunkModel(
                        user_id=row.user_id,
                        source=row.source,
                        source_id=row.source_id,
                        generation=row.generation,
                        version=row.version,
                        number=number,
                        start=chunk.start,
                        end=chunk.end,
                        body=chunk.text,
                        locator=chunk.locator,
                        digest=chunk.digest,
                        embedding=vector,
                    )
                )
            row.lease_until, row.updated_at = self.now() + timedelta(minutes=2), self.now()
            return True

    def finish(self, work: IndexWork) -> bool:
        with self.sessions.begin() as database:
            row = self.current(database, work)
            if row is None:
                return False
            row.status, row.lease, row.lease_until, row.updated_at = "ready", None, None, self.now()
            return True

    def fail(self, work: IndexWork) -> None:
        with self.sessions.begin() as database:
            row = self.current(database, work)
            if row is not None:
                row.status, row.error, row.lease, row.lease_until = (
                    "failed",
                    "indexing_failed",
                    None,
                    None,
                )

    def retry(self, user_id: UUID, source: str, source_id: UUID) -> bool:
        with self.sessions.begin() as database:
            if (
                not SqlAlchemyUserAuthentication(database).lock_active(user_id)
                or SqlAlchemySourceDocuments(database).read(user_id, source, source_id) is None
            ):
                return False
            row = database.get(
                IndexSourceModel,
                (user_id, source, source_id, self.generation),
                with_for_update=True,
            )
            if row is not None and row.status == "failed":
                row.status, row.attempts, row.error = "pending", 0, None
            return True
