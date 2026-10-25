import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from celery import Celery
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.logging import log_failure
from app.modules.materials.application.ports import MaterialStorage, TextExtractor
from app.modules.materials.application.processing import MaterialProcessingService
from app.modules.materials.application.service import MaterialService
from app.modules.materials.infrastructure.extractor import BoundedDocumentExtractor
from app.modules.materials.infrastructure.orm import MaterialModel
from app.modules.materials.infrastructure.repository import SqlAlchemyMaterialRepository
from app.modules.search.infrastructure.documents import SqlAlchemyMaterialTextIndex
from app.modules.search.infrastructure.orm import MaterialSearchDocumentModel
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication

logger = logging.getLogger(__name__)


class MaterialJobUnavailable(Exception):
    pass


def processing_service(
    database: Session,
    storage: MaterialStorage,
    extractor: TextExtractor,
    now: Callable[[], datetime],
) -> MaterialProcessingService:
    return MaterialProcessingService(
        SqlAlchemyMaterialRepository(database),
        SqlAlchemyUserAuthentication(database),
        storage,
        extractor,
        SqlAlchemyMaterialTextIndex(database),
        now=now,
    )


def process_material(
    sessions: sessionmaker[Session],
    storage: MaterialStorage,
    extractor: TextExtractor,
    material_id: UUID,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> None:
    with sessions.begin() as database:
        material = SqlAlchemyMaterialRepository(database).system_get(material_id)
        if material is None:
            return
        work = processing_service(database, storage, extractor, now).claim(
            material.user_id, material_id
        )
    if work is None:
        return
    with sessions() as database:
        result = processing_service(database, storage, extractor, now).execute(work)
    with sessions.begin() as database:
        processing_service(database, storage, extractor, now).complete(work, result)


def dispatch_materials(
    sessions: sessionmaker[Session],
    storage: MaterialStorage,
    celery: Celery,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    reextract_legacy: bool = False,
) -> None:
    if reextract_legacy:
        with sessions() as database:
            old = list(
                database.execute(
                    select(MaterialModel.user_id, MaterialModel.id)
                    .join(
                        MaterialSearchDocumentModel,
                        MaterialSearchDocumentModel.material_id == MaterialModel.id,
                    )
                    .where(
                        MaterialModel.status == "ready",
                        MaterialModel.trashed_at.is_(None),
                        MaterialSearchDocumentModel.extraction_revision == 0,
                    )
                    .limit(100)
                )
            )
        for user_id, material_id in old:
            with sessions.begin() as database:
                processing_service(
                    database, storage, BoundedDocumentExtractor(), now
                ).reextract_legacy(user_id, material_id)
    with sessions.begin() as database:
        repository = SqlAlchemyMaterialRepository(database)
        cleanup, orphans = repository.cleanup_candidates(now()), repository.orphan_ids()
    failed = False
    for user_id, material_id in cleanup:
        try:
            with sessions.begin() as database:
                MaterialService(
                    SqlAlchemyMaterialRepository(database),
                    SqlAlchemyUserAuthentication(database),
                    storage,
                    now=now,
                ).purge_expired(user_id, material_id)
        except Exception as error:
            failed = True
            log_failure(logger, "materials.cleanup_failed", error)
    for object_id in orphans:
        try:
            with sessions.begin() as database:
                repository = SqlAlchemyMaterialRepository(database)
                key = repository.orphan_key(object_id)
                if key is not None:
                    storage.delete(key)
                    repository.remove_orphan(object_id)
        except Exception as error:
            failed = True
            log_failure(logger, "materials.cleanup_failed", error)
    with sessions.begin() as database:
        candidates = SqlAlchemyMaterialRepository(database).processing_candidates(now())
    for material_id in candidates:
        try:
            celery.send_task(
                "materials.process", kwargs={"material_id": str(material_id)}, queue="materials"
            )
        except Exception as error:
            failed = True
            log_failure(logger, "materials.dispatch_failed", error)
    if failed:
        raise MaterialJobUnavailable("Material maintenance is unavailable.")
